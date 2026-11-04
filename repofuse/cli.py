"""RepoFuse CLI.

  python -m repofuse run <repo_url> <repo_url>... --out <dir>

Stages: ingest -> analyze -> plan -> synthesize -> verify -> report.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import ingest as ingest_mod
from . import analyze as analyze_mod
from . import safety as safety_mod
from . import plan as plan_mod
from . import synthesize as synth_mod
from . import verify as verify_mod
from . import report as report_mod
from . import heal as heal_mod
from . import vendor as vendor_mod
from . import acceptance as accept_mod
from .qualification import target as qual_target
from . import package as package_mod
from . import gluereview


def _synthesis_stage(manifest, metas, out, fusion_dir, glue_reviewed):
    """Run synthesis, or reuse the existing glue on a re-run: re-synthesizing
    would produce NEW unreviewed bytes and spend budget again, so ANY re-run
    with a completed synthesis reuses the existing bytes byte-for-byte. To
    force regeneration, delete fused_app/generated/ first (an explicit,
    visible act; budget is durable and never resets either way)."""
    syn_path = os.path.join(out, "synthesis.json")
    if os.path.isfile(syn_path):
        prior = json.load(open(syn_path))
        if prior.get("status") == "completed" and \
                gluereview.generated_targets(fusion_dir):
            print("synthesis: reusing existing glue (no new model call)")
            prior["_reused"] = True
            return prior
    synthesis = synth_mod.run_synthesis(manifest, metas, out)
    ingest_mod.save_json(synthesis, syn_path)
    print(f"synthesis: {synthesis['status']}")
    return synthesis


def _refuse_same_invocation_attestation(args, synthesis):
    """--glue-reviewed attests bytes the operator ALREADY reviewed. If this
    same invocation just generated new glue, those bytes were never
    reviewed, so attesting now would be self-attestation: refuse. Review
    the new files, then re-run with --glue-reviewed (synthesis is reused,
    no new spend)."""
    if (args.glue_reviewed and synthesis.get("files_written")
            and not synthesis.get("_reused")):
        print("refused: this invocation generated new glue; "
              "--glue-reviewed may only attest previously existing, "
              "already-reviewed bytes. Review generated/ and re-run.",
              file=sys.stderr)
        return True
    return False


def _attestation_stage(fusion_dir, out, glue_reviewed):
    """--glue-reviewed means: the operator states they have source-reviewed
    the CURRENT glue bytes (unittest/runner/introspection/hmac/ctypes/gc
    monkeypatching or equivalent interference). We pin those exact bytes;
    any later change re-gates execution."""
    if not glue_reviewed:
        return None
    attestation = os.path.join(out, "glue_review.attestation.json")
    doc = gluereview.write_attestation(fusion_dir, attestation)
    print(f"glue review attestation: {len(doc['files'])} file(s) pinned")
    return attestation


def cmd_run(args):
    out = os.path.abspath(args.out)
    workdir = os.path.join(out, "repos")
    os.makedirs(workdir, exist_ok=True)
    metas = []
    for url in args.repos:
        meta = ingest_mod.ingest(url, workdir,
                                 allow_local=args.allow_local)
        if meta.get("clone_error"):
            print(f"clone failed for {url}: {meta['clone_error']}", file=sys.stderr)
            return 2
        metas.append(meta)
        print(f"ingested {meta['slug']} @ {meta['commit_sha'][:12]} "
              f"license={meta['license_guess'] or 'NONE FOUND'}")
    ingest_mod.save_json(metas, os.path.join(out, "ingest.json"))

    analyses = [analyze_mod.analyze(m) for m in metas]
    ingest_mod.save_json(analyses, os.path.join(out, "analysis.json"))

    # Safety qualification runs BEFORE any vendoring, synthesis spend, or
    # execution. fail or unknown (any required check missing) blocks
    # outright; an unacknowledged warn blocks spend/execution (vendoring
    # is only copying, so it may proceed and leave evidence).
    verdicts = [safety_mod.qualify_repo(
        m["slug"], m["path"], deps=a.get("dependencies", {}),
        repo_commit=m.get("commit_sha"),
        allow_network=args.safety_network) for m, a in zip(metas, analyses)]
    run_verdict = safety_mod.qualify_run(
        verdicts, warnings_acknowledged=args.ack_safety_warnings,
        acknowledged_via="--ack-safety-warnings CLI flag"
        if args.ack_safety_warnings else None)
    ingest_mod.save_json(run_verdict, os.path.join(out, "safety.json"))
    print(f"safety: {run_verdict['status']} "
          f"(blocking: {run_verdict['blocking']})")
    for v in verdicts:
        print(f"  {v['repo']}: {v['status']} - "
              f"static {v['static']['status']} "
              f"({len(v['static']['findings'])} finding(s)); "
              f"deps {v['dependencies']['status']}: "
              f"{v['dependencies']['note']}")
    hard_block = any(v["blocking"] for v in verdicts)
    if hard_block:
        print("safety qualification BLOCKING: a required check failed or "
              "is unknown; refusing to vendor, synthesize, or execute. "
              "Offline runs cannot check known vulnerabilities - re-run "
              "with --safety-network for the bounded advisory read.",
              file=sys.stderr)
        return 2
    warn_pending = (run_verdict["status"] == "warn"
                    and not args.ack_safety_warnings)

    manifest = plan_mod.build_manifest(metas, analyses)
    ingest_mod.save_json(manifest, os.path.join(out, "fuse_manifest.json"))
    print(f"manifest: {len(manifest['conflicts'])} conflict(s), "
          f"{len(manifest['boundary_candidates'])} boundary candidate(s)")

    criteria = accept_mod.derive_criteria(manifest, analyses)
    ingest_mod.save_json(criteria, os.path.join(out, "acceptance.json"))
    manifest["acceptance_criteria"] = criteria
    print(f"acceptance criteria: {len(criteria)}")

    vendor_manifest = vendor_mod.vendor_repos(
        metas, os.path.join(out, "fused_app"))
    vendor_mod.write_import_shim(os.path.join(out, "fused_app"))
    ingest_mod.save_json(vendor_manifest, os.path.join(out, "vendor_manifest.json"))
    print(f"vendored {len(vendor_manifest['repos'])} repo(s) "
          f"({len(vendor_manifest['hashes'])} files hashed)")

    if warn_pending:
        print("safety WARN present: spending and execution require an "
              "explicit reviewer acknowledgment. Vendored evidence was "
              "left in place; re-run with --ack-safety-warnings after "
              "review to proceed. Note: acknowledgment clears only this "
              "gate - execution still requires isolation and independent "
              "review of the exact vendored and generated bytes.",
              file=sys.stderr)
        return 2

    fusion_dir = os.path.join(out, "fused_app")
    synthesis = _synthesis_stage(manifest, metas, out, fusion_dir,
                                 args.glue_reviewed)
    if _refuse_same_invocation_attestation(args, synthesis):
        return 2
    attestation = _attestation_stage(fusion_dir, out, args.glue_reviewed)

    verification = verify_mod.verify_fused_app(
        fusion_dir, attestation_path=attestation)
    verification["independence"] = accept_mod.check_test_independence(
        fusion_dir, os.path.join(fusion_dir, "vendor"))
    if verification.get("status") == "passed":
        verification["vacuity_control"] = verify_mod.vacuity_control(
            fusion_dir, synthesis.get("files_written", []),
            attestation_path=attestation)
        if verification["vacuity_control"]["status"] == "vacuous_tests":
            verification["status"] = "rejected_vacuous"
    heal = (heal_mod.auto_heal(out, verification, attestation_path=attestation)
            if synthesis.get("status") == "completed"
            else {"status": "not_attempted",
                  "reason": "synthesis not completed; heal only fixes real "
                            "generated code"})
    if heal.get("second_verify"):
        verification = heal["second_verify"]
        verification["healed"] = True
    verification["heal"] = heal
    ingest_mod.save_json(verification, os.path.join(out, "verification.json"))
    print(f"verify: {verification['status']} (heal: {heal['status']})")

    pkg = package_mod.package_fused_app(out)
    ingest_mod.save_json(pkg, os.path.join(out, "package.json"))
    print(f"package: {pkg['status']}")

    report_mod.build_report(out, metas, manifest, synthesis, verification)
    print(f"report: {os.path.join(out, 'report.json')}")
    return 0


def cmd_qualify(args):
    """Pinned qualification: fixed inputs, fixed contract, fixed acceptance."""
    out = os.path.abspath(args.out)
    workdir = os.path.join(out, "repos")
    os.makedirs(workdir, exist_ok=True)
    metas = []
    for slug, spec in qual_target.TARGET["inputs"].items():
        meta = ingest_mod.ingest(spec["url"], workdir,
                                 expected_sha=spec["commit"])
        if meta.get("clone_error"):
            print(f"pinned ingest failed for {slug}: {meta['clone_error']}",
                  file=sys.stderr)
            return 2
        metas.append(meta)
        print(f"pinned ingest {slug} @ {meta['commit_sha'][:12]} "
              f"license={meta['license_guess']}")
    ingest_mod.save_json(metas, os.path.join(out, "ingest.json"))
    analyses = [analyze_mod.analyze(m) for m in metas]
    ingest_mod.save_json(analyses, os.path.join(out, "analysis.json"))
    manifest = plan_mod.build_manifest(metas, analyses)
    manifest["qualification_contract"] = qual_target.TARGET["contract"]
    criteria = accept_mod.derive_criteria(manifest, analyses)
    manifest["acceptance_criteria"] = criteria
    ingest_mod.save_json(manifest, os.path.join(out, "fuse_manifest.json"))

    fusion_dir = os.path.join(out, "fused_app")
    vendor_manifest = vendor_mod.vendor_repos(metas, fusion_dir)
    vendor_mod.write_import_shim(fusion_dir)
    ingest_mod.save_json(vendor_manifest,
                         os.path.join(out, "vendor_manifest.json"))
    print(f"vendored {len(vendor_manifest['repos'])} pinned repo(s) "
          f"({len(vendor_manifest['hashes'])} files, readback-verified)")

    synthesis = _synthesis_stage(manifest, metas, out, fusion_dir,
                                 args.glue_reviewed)
    if _refuse_same_invocation_attestation(args, synthesis):
        return 2
    attestation = _attestation_stage(fusion_dir, out, args.glue_reviewed)

    # FIXED acceptance test is decisive; model test is supplementary
    acc_path = os.path.join(fusion_dir, "acceptance_test.py")
    with open(acc_path, "w", encoding="utf-8") as f:
        f.write(qual_target.ACCEPTANCE_TEST)
    acceptance = verify_mod.verify_fused_app(
        fusion_dir, test_module="acceptance_test",
        attestation_path=attestation)
    if acceptance.get("status") == "passed":
        acceptance["vacuity_control"] = verify_mod.vacuity_control(
            fusion_dir, synthesis.get("files_written", []),
            test_module="acceptance_test", attestation_path=attestation)
        if acceptance["vacuity_control"]["status"] == "vacuous_tests":
            acceptance["status"] = "rejected_vacuous"
    ingest_mod.save_json(acceptance, os.path.join(out, "acceptance_result.json"))
    print(f"ACCEPTANCE (fixed, decisive): {acceptance['status']}")

    supplementary = verify_mod.verify_fused_app(
        fusion_dir, attestation_path=attestation)
    ingest_mod.save_json(supplementary, os.path.join(out, "verification.json"))
    print(f"model-test (supplementary): {supplementary['status']}")

    heal = (heal_mod.auto_heal(out, acceptance, attestation_path=attestation)
            if synthesis.get("status") == "completed"
            else {"status": "not_attempted",
                  "reason": "synthesis not completed; heal only fixes real "
                            "generated code"})
    ingest_mod.save_json(heal, os.path.join(out, "heal.json"))
    pkg = package_mod.package_fused_app(out)
    report_mod.build_report(out, metas, manifest, synthesis, acceptance)
    print(f"report: {os.path.join(out, 'report.json')}")
    return 0 if acceptance.get("status") == "passed" else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="repofuse",
                                description="Multi-repository synthesis engine prototype")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="full pipeline")
    run.add_argument("repos", nargs="+", help="git URLs or local paths (2+)")
    run.add_argument("--out", required=True, help="output/work directory")
    run.add_argument("--allow-local", action="store_true",
                     help="permit local directory paths as inputs (dev/test only)")
    run.add_argument("--safety-network", action="store_true",
                     help="allow the bounded osv.dev advisory read "
                          "(repo commit + pinned direct dependency "
                          "name/version/ecosystem only); offline runs "
                          "report the vuln check as unknown, which blocks")
    run.add_argument("--ack-safety-warnings", action="store_true",
                     help="acknowledge warn-level safety findings after "
                          "review; without this a warn blocks spending "
                          "and execution")
    run.set_defaults(func=cmd_run)
    run.add_argument("--glue-reviewed", action="store_true",
                     help="attest the current glue bytes were source-reviewed")
    qual = sub.add_parser("qualify", help="pinned qualification run")
    qual.add_argument("--out", required=True)
    qual.add_argument("--glue-reviewed", action="store_true",
                      help="attest the current glue bytes were source-reviewed")
    qual.set_defaults(func=cmd_qualify)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
