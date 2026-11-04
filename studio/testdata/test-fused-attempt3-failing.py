import vendor
import microdot
import peewee
import generated.app as gen_app
from microdot.test_client import TestClient

app = gen_app.app
db = gen_app.db
MODELS = gen_app.MODELS

def _setup_db():
    db.init(':memory:')
    db.connect(reuse_if_open=True)
    db.create_tables(MODELS, safe=True)
    for m in MODELS:
        m.delete().execute()

_setup_db()
client = TestClient(app)

def test_create():
    r = client.post('/notes', json={'title': 't1', 'content': 'c1', 'pinned': False})
    assert r.status_code == 201, r.text
    data = r.json
    assert isinstance(data, dict) and 'id' in data
    return data['id']

def test_list_expects(nid):
    r = client.get('/notes')
    assert r.status_code == 200, r.text
    data = r.json
    assert isinstance(data, list)
    assert any(isinstance(x, dict) and x.get('id') == nid for x in data)

def test_read(nid):
    r = client.get(f'/notes/{nid}')
    assert r.status_code == 200, r.text
    assert isinstance(r.json, dict)
    assert r.json.get('id') == nid
    r2 = client.get('/notes/999999')
    assert r2.status_code == 404, r2.text

def test_update(nid):
    r = client.put(f'/notes/{nid}', json={'title': 't2', 'content': 'c2', 'pinned': True})
    assert r.status_code == 200, r.text
    assert isinstance(r.json, dict)
    r2 = client.get(f'/notes/{nid}')
    assert r2.status_code == 200
    assert r2.json.get('title') == 't2'

def test_delete(nid):
    r = client.delete(f'/notes/{nid}')
    assert r.status_code == 204, r.text
    r2 = client.get(f'/notes/{nid}')
    assert r2.status_code == 404, r2.text

def test_full_crud():
    _setup_db()
    nid = test_create()
    test_list_expects(nid)
    test_read(nid)
    test_update(nid)
    test_delete(nid)

if __name__ == '__main__':
    test_full_crud()
    print('ok')
