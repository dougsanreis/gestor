"""Test suite for syra_core.

Every test is hermetic: no network, no writes outside a temporary directory, no
sleeps. A suite that is slow or flaky is a suite people stop running, and a
suite people stop running is worse than no suite at all -- it provides
confidence without providing evidence.
"""
