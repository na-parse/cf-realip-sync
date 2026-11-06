'''Unit tests for cf-realip-sync (stdlib only: python3 -m unittest).'''
import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

# =============================================================================
# Load the extensionless script as a module
# =============================================================================
SCRIPT = Path(__file__).resolve().parent.parent / 'cf-realip-sync'
_loader = importlib.machinery.SourceFileLoader('cf_realip_sync', str(SCRIPT))
_spec = importlib.util.spec_from_loader('cf_realip_sync', _loader)
crs = importlib.util.module_from_spec(_spec)
sys.modules['cf_realip_sync'] = crs
_loader.exec_module(crs)

V4 = [f'10.{i}.0.0/16' for i in range(12)]
V6 = [f'2001:db8:{i}::/48' for i in range(6)]


def _cfg(output: Path) -> 'crs.Config':
    '''Default config pointed at a temp output, with harmless commands.'''
    cfg = crs.load_config(crs.DEFAULT_CONFIG)
    cfg.output = output
    cfg.test_cmd = ['true']
    cfg.reload_cmd = ['true']
    cfg.notify_on_change = False
    return cfg


# =============================================================================
# Tests
# =============================================================================
class ParseRanges(unittest.TestCase):
    '''parse_ranges validation.'''

    def test_valid_keeps_order(self) -> None:
        '''Valid lines come back in order, blanks skipped.'''
        text = '\n'.join(V4[:3]) + '\n\n'
        self.assertEqual(crs.parse_ranges(text, 4), V4[:3])

    def test_rejects_garbage(self) -> None:
        '''An HTML error page is not a list.'''
        with self.assertRaises(crs.SyncError):
            crs.parse_ranges('<html>oops</html>', 4)

    def test_rejects_wrong_family(self) -> None:
        '''An IPv6 range in the IPv4 list fails.'''
        with self.assertRaises(crs.SyncError):
            crs.parse_ranges(V6[0], 4)

    def test_rejects_host_bits(self) -> None:
        '''strict=True: host bits set is an error.'''
        with self.assertRaises(crs.SyncError):
            crs.parse_ranges('10.0.0.1/16', 4)

    def test_rejects_duplicates(self) -> None:
        '''A repeated range fails.'''
        with self.assertRaises(crs.SyncError):
            crs.parse_ranges(f'{V4[0]}\n{V4[0]}', 4)


class Sanity(unittest.TestCase):
    '''check_sanity limits.'''

    def setUp(self) -> None:
        self.cfg = _cfg(Path('unused'))

    def test_ok(self) -> None:
        '''Full lists pass.'''
        crs.check_sanity(self.cfg, V4, V6, V4 + V6)

    def test_short_list(self) -> None:
        '''Too few IPv4 ranges fails.'''
        with self.assertRaises(crs.SyncError):
            crs.check_sanity(self.cfg, V4[:3], V6, [])

    def test_large_removal(self) -> None:
        '''Dropping most current ranges fails.'''
        current = [f'192.0.{i}.0/24' for i in range(30)]
        with self.assertRaises(crs.SyncError):
            crs.check_sanity(self.cfg, V4, V6, current)


class RenderAndInstall(unittest.TestCase):
    '''render, ranges_in, install and rollback.'''

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / 'cloudflare-realip.conf'
        self.cfg = _cfg(self.out)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_render_roundtrip(self) -> None:
        '''ranges_in recovers what render wrote; output is deterministic.'''
        text = crs.render(self.cfg, V4, V6)
        self.assertEqual(crs.ranges_in(text), V4 + V6)
        self.assertEqual(text, crs.render(self.cfg, V4, V6))
        self.assertIn('real_ip_header CF-Connecting-IP;', text)

    def test_ranges_in_joined_lines(self) -> None:
        '''Joined directives both count; commented-out ones do not.'''
        text = ('set_real_ip_from 10.0.0.0/8;set_real_ip_from 2001:db8::/32;\n'
                '  set_real_ip_from 192.0.2.0/24 ;\n'
                '# set_real_ip_from 198.51.100.0/24;\n')
        self.assertEqual(crs.ranges_in(text),
                         ['10.0.0.0/8', '2001:db8::/32', '192.0.2.0/24'])

    def test_install_success(self) -> None:
        '''New file installed, previous kept as .prev.'''
        self.out.write_text('old\n')
        crs.install(self.cfg, 'old\n', 'new\n')
        self.assertEqual(self.out.read_text(), 'new\n')
        self.assertEqual(self.out.with_name(self.out.name + '.prev')
                         .read_text(), 'old\n')

    def test_install_rollback(self) -> None:
        '''A failing nginx test restores the old file and raises.'''
        self.out.write_text('old\n')
        self.cfg.test_cmd = [sys.executable, '-c',
                             f'import sys; sys.exit(open({str(self.out)!r})'
                             f'.read() == "new\\n")']
        with self.assertRaises(crs.SyncError) as ctx:
            crs.install(self.cfg, 'old\n', 'new\n')
        self.assertEqual(self.out.read_text(), 'old\n')
        self.assertIn('restored, nginx test passes', str(ctx.exception))

    def test_install_rollback_no_previous(self) -> None:
        '''With no previous file, a failed test removes the new one.'''
        self.cfg.test_cmd = ['false']
        with self.assertRaises(crs.SyncError):
            crs.install(self.cfg, None, 'new\n')
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
