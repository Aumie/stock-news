"""Real check for a bug reported live: st.navigation(build_pages()) raised
StreamlitAPIException("Multiple Pages specified with URL pathname render...")
because every views/*.py module names its entry point `render`, and
st.Page() infers a URL pathname from the callable's own name when none is
given — all four collided on "render". Fixed by passing explicit url_path=
to each st.Page().

st.navigation()'s own pathname-collision check only runs inside a real
Streamlit script-run context (confirmed: calling it from a bare `python`
script does not raise, even with the exact buggy code) — so this uses
Streamlit's AppTest harness, which provides a real one, rather than a plain
unit test. This is the actual repro of the live crash, not a proxy for it.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

_SCRIPT = """
import streamlit as st
from views.navigation import build_pages
st.navigation(build_pages()).run()
"""


def test_navigation_does_not_raise_url_pathname_collision():
    at = AppTest.from_string(_SCRIPT)
    at.run()

    assert at.exception == []
