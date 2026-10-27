#!/usr/bin/env python3
"""P6 producer/verifier wire-budget regression tests; no model or network calls."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bridge'))
import evidence


def protocol_fixture(text):
    """Independent canonical wire fixture matching the public cxpan.evidence/1 schema."""
    data = text.encode('utf-8')
    return json.dumps({
        'schema': 'cxpan.evidence/1', 'repo_id': 'agent-loop',
        'path': 'docs/SPEC.md', 'sha256': hashlib.sha256(data).hexdigest(),
        'size_bytes': len(data), 'line_count': len(text.splitlines()), 'text': text,
    }, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class CapsuleWireBudgetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='p6-wire-budget-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'docs').mkdir()
        self.source = self.root / 'docs/SPEC.md'

    def put(self, text):
        self.source.write_bytes(text.encode('utf-8'))

    def test_capture_rejects_control_character_expansion_before_return(self):
        text = '\x01' * 10000
        self.assertEqual(len(protocol_fixture(text).encode('utf-8')), 60194)
        self.put(text)
        with self.assertRaisesRegex(ValueError, 'serialized capsule.*quota'):
            evidence.capture(self.root, 'docs/SPEC.md')

    def test_capture_and_verify_accept_exact_40000_byte_boundary(self):
        # 6634 six-byte JSON escapes + 3 ASCII bytes + 193 metadata bytes.
        text = '\x01' * 6634 + 'xxx'
        self.put(text)
        capsule = evidence.capture(self.root, 'docs/SPEC.md')
        self.assertEqual(len(capsule.encode('utf-8')), 40000)
        digest = hashlib.sha256(capsule.encode('utf-8')).hexdigest()
        self.assertEqual(evidence.verify(capsule, digest)['text'], text)

    def test_capture_rejects_40001_byte_boundary(self):
        text = '\x01' * 6634 + 'xxxx'
        self.assertEqual(len(protocol_fixture(text).encode('utf-8')), 40001)
        self.put(text)
        with self.assertRaisesRegex(ValueError, 'serialized capsule.*quota'):
            evidence.capture(self.root, 'docs/SPEC.md')

    def test_verifier_still_rejects_40001_bytes_without_relaxing_cap(self):
        raw = protocol_fixture('\x01' * 6634 + 'xxxx')
        with self.assertRaisesRegex(ValueError, 'invalid capsule type/length'):
            evidence.verify(raw)

    def test_capture_uses_utf8_wire_bytes_not_python_character_count(self):
        text = '\x01' * 6200 + '汉' * 1000
        raw = protocol_fixture(text)
        self.assertEqual(len(raw), 38393)
        self.assertEqual(len(raw.encode('utf-8')), 40393)
        self.put(text)
        with self.assertRaisesRegex(ValueError, 'serialized capsule.*quota'):
            evidence.capture(self.root, 'docs/SPEC.md')

    def test_regular_inputs_keep_exact_canonical_bytes_and_round_trip(self):
        for text in ('', 'ASCII\r\n中文\n', '"\\' * 5000,
                     '\x01' * 6000, 'x' * 18000, 'x\n' * 650):
            with self.subTest(chars=len(text)):
                self.put(text)
                raw = evidence.capture(self.root, 'docs/SPEC.md')
                self.assertEqual(raw, protocol_fixture(text))
                self.assertLessEqual(len(raw.encode('utf-8')), 40000)
                self.assertEqual(evidence.verify(raw)['text'], text)

    def test_existing_source_limits_and_allowlist_remain_enforced(self):
        for text in ('x' * 18001, 'x\n' * 651, 'x\x00y'):
            with self.subTest(chars=len(text)):
                self.put(text)
                with self.assertRaises(ValueError):
                    evidence.capture(self.root, 'docs/SPEC.md')
        self.put('normal')
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            evidence.capture(self.root, 'docs/not-approved.md')

    def test_two_digests_still_detect_modified_capsule_and_source(self):
        self.put('Trusted original')
        raw = evidence.capture(self.root, 'docs/SPEC.md')
        outer = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        tampered = raw.replace('Trusted original', 'Corrupt original')
        with self.assertRaisesRegex(ValueError, 'task result SHA'):
            evidence.verify(tampered, outer)
        with self.assertRaisesRegex(ValueError, 'source content SHA'):
            evidence.verify(tampered)


if __name__ == '__main__':
    unittest.main()
