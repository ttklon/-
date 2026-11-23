"""Run tests and surface failure messages as GitHub annotations."""
import unittest

suite = unittest.defaultTestLoader.discover('tests')
result = unittest.TextTestRunner(verbosity=2).run(suite)
for test, detail in result.failures + result.errors:
    safe_detail = detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f'::error title=Test failure::{test.id()}%0A{safe_detail}', flush=True)
raise SystemExit(not result.wasSuccessful())
