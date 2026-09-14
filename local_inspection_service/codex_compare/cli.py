#!/usr/bin/env python3
"""Dependency-free vantaline CLI, available inside each isolated Codex task."""
import argparse
import base64
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import uuid


class SocketHTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(20)
        self.sock.connect(os.environ['VANTALINE_TASK_SOCKET'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-id', default=None, help='Reuse the same ID only to retry an identical write')
    groups = parser.add_subparsers(dest='group', required=True)
    task = groups.add_parser('task').add_subparsers(dest='action', required=True)
    task.add_parser('show')
    card = groups.add_parser('card').add_subparsers(dest='action', required=True)
    card.add_parser('show')
    card.add_parser('progress').add_argument('--message', required=True)
    card.add_parser('finalize')
    card.add_parser('summary').add_subparsers(dest='verb', required=True).add_parser('set').add_argument('--file', required=True)
    for group, verb in [('element', 'upsert'), ('checklist', 'set'), ('check', 'upsert'), ('issue', 'upsert')]:
        groups.add_parser(group).add_subparsers(dest='action', required=True).add_parser(verb).add_argument('--file', required=True)
    images = groups.add_parser('image').add_subparsers(dest='action', required=True)
    decode = images.add_parser('decode')
    decode.add_argument('--source', required=True, choices=['reference', 'actual'])
    decode.add_argument('--box', default='[0,0,1,1]')
    crop = images.add_parser('crop')
    crop.add_argument('--source', required=True, choices=['reference', 'actual'])
    crop.add_argument('--box', required=True, help='Original normalized XYWH')
    crop.add_argument('--file', required=True)
    crop.add_argument('--scale', type=float, default=1)
    coords = images.add_parser('map')
    coords.add_argument('--box', required=True, help='Normalized XYWH within crop')
    coords.add_argument('--crop', required=True, help='Original normalized crop XYWH')
    report = groups.add_parser('report').add_subparsers(dest='action', required=True)
    report.add_parser('progress').add_argument('--message', required=True)
    for name, verb in [('item', 'upsert'), ('summary', 'set')]:
        report.add_parser(name).add_subparsers(dest='verb', required=True).add_parser(verb).add_argument('--file', required=True)
    report.add_parser('finalize')
    artifact = groups.add_parser('artifact').add_subparsers(dest='action', required=True).add_parser('add')
    artifact.add_argument('--file', required=True)
    artifact.add_argument('--source', choices=['reference', 'actual'], required=True)
    artifact.add_argument('--box', required=True, help='Original normalized [x,y,width,height] crop bounds')
    args = parser.parse_args()
    payload = {}
    if args.group == 'image' and args.action in {'crop', 'map'}:
        from image_tools import local_image
        print(json.dumps(local_image(args)))
        return
    if args.group == 'task' or (args.group == 'card' and args.action == 'show'):
        kind = 'show'
    elif args.group == 'image':
        kind = 'decode'
        payload = {'source': args.source, 'box': json.loads(args.box)}
    elif args.group == 'artifact':
        kind = 'artifact'
        path = Path(args.file).resolve()
        if not path.is_relative_to(Path('/work')) or path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError('Evidence must be a bounded file inside /work')
        payload = {'data': base64.b64encode(path.read_bytes()).decode(), 'source': args.source, 'box': json.loads(args.box)}
    else:
        kind = args.group if args.group in {'element', 'checklist', 'check', 'issue'} else args.action
        if kind in {'item', 'summary', 'element', 'checklist', 'check', 'issue'}:
            path = Path(args.file)
            if path.stat().st_size > 65536:
                raise ValueError('JSON payload too large')
            payload = json.loads(path.read_text())
        elif kind == 'progress':
            payload = {'message': args.message}
    connection = SocketHTTP('localhost')
    connection.request('POST', '/', json.dumps({'kind': kind, 'payload': payload, 'key': args.request_id or uuid.uuid4().hex}),
                       {'Authorization': 'Bearer ' + os.environ['VANTALINE_TASK_TOKEN'], 'Content-Type': 'application/json'})
    response = connection.getresponse()
    body = response.read(16 * 1024 * 1024).decode()
    print(body)
    if response.status >= 400:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
