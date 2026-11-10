"""표(st.data_editor / st.dataframe) 제목줄과 고르기 칸 글자를 가운데로 (2026-11-10, 노신 승인).

Streamlit 표는 글자를 그림(canvas)으로 그려서 CSS가 안 먹고, column_config 의 alignment 도
칸 안 글자에만 적용돼요. 제목줄과 고르기(selectbox) 칸은 항상 왼쪽에 그리게 되어 있어서,
앱이 켜질 때 Streamlit 화면 파일(DataFrame.*.js)에서 그 두 곳만 '가운데'로 바꿔 둡니다.
Streamlit 버전이 바뀌어 고칠 문장을 못 찾으면 아무것도 하지 않아요 (표는 원래대로 동작).
"""
from __future__ import annotations

import os
from pathlib import Path

PATCHES = [
    # 제목줄 글자
    ("if(m&&(e.textAlign=`right`),h.textBounds!==void 0&&e.fillText(a.title,m?h.textBounds.x+h.textBounds.width:h.textBounds.x,"
     "n+i/2+io(e,s.headerFontFull)),m&&(e.textAlign=`left`)",
     "if(e.textAlign=`center`,h.textBounds!==void 0&&e.fillText(a.title,(h.textBounds.x+t+r)/2,"
     "n+i/2+io(e,s.headerFontFull)),e.textAlign=`left`"),
    # 고르기(selectbox) 칸 글자
    ("n.fillText(s,i.x+r.cellHorizontalPadding,i.y+i.height/2+io(n,r))",
     "(n.textAlign=`center`,n.fillText(s,i.x+i.width/2,i.y+i.height/2+io(n,r)),n.textAlign=`left`)"),
]


def apply() -> int:
    """고친 파일 수. 이미 고쳤거나 못 찾으면 0."""
    try:
        import streamlit
        js = Path(os.path.dirname(streamlit.__file__)) / "static" / "static" / "js"
        n = 0
        for f in js.glob("DataFrame.*.js"):
            s = f.read_text(encoding="utf-8")
            t = s
            for a, b in PATCHES:
                t = t.replace(a, b)
            if t != s:
                f.write_text(t, encoding="utf-8")
                n += 1
        return n
    except Exception:  # 읽기 전용 설치 등: 그냥 넘어감
        return 0
