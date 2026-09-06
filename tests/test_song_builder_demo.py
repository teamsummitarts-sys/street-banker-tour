"""Actual browser-generated demo bytes through the multipart upload boundary."""
import json
from pathlib import Path
import subprocess
import base64

from test_song_builder_backend import host, auth_headers


def test_all_demo_layers_upload_with_webkit_multipart_boundary(tmp_path):
    result = subprocess.run(['node', '--input-type=module', '-e',
        "import {createDemoAudio} from './song_builder/static/core/audio.mjs';"
        "console.log(JSON.stringify(createDemoAudio().map(d=>({name:d.name,"
        "data:Buffer.from(d.buffer).toString('base64')}))));"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
    app, _ = host(tmp_path)
    client = app.test_client()
    headers = auth_headers(client)
    for demo in json.loads(result.stdout):
        boundary = '----WebKitFormBoundaryabcdefghijkl'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{demo["name"]}.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode()
        body += base64.b64decode(demo['data'])
        body += f'\r\n--{boundary}--\r\n'.encode()
        response = client.post('/song-builder/api/assets', headers=headers, data=body,
                               content_type='multipart/form-data; boundary=' + boundary)
        assert response.status_code == 201, (demo['name'], response.json)
        assert response.json['asset']['duration'] == 8
