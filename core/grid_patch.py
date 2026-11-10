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


# 브라우저가 옛 DataFrame 화면 파일을 1년간 저장해 두면(캐시) 위 고침이 안 보이므로,
# 화면에서 직접 그림 도구(canvas)를 가로채 '왼쪽 정렬로 그리는 글자'를 칸 가운데로 옮김.
# 이미 가운데로 그려진 글자는 건드리지 않아서 위 고침과 함께 써도 안전.
RUNTIME_JS = """
(function(){
  var W = window; if (W.__gridCenter) return; W.__gridCenter = 1;
  var P = W.CanvasRenderingContext2D && W.CanvasRenderingContext2D.prototype; if (!P) return;
  var rect = P.rect, ft = P.fillText, memo = new WeakMap();
  function inGrid(c){
    var v = memo.get(c);
    if (v === undefined){
      v = !!(c && c.closest && c.closest('[data-testid="stDataFrame"],[data-testid="stDataFrameGlideDataEditor"]'));
      if (v) memo.set(c, v);
    }
    return v;
  }
  P.rect = function(x, y, w, h){ this.__r = [x, y, w, h]; return rect.apply(this, arguments); };
  var di = P.drawImage;
  P.drawImage = function(img, x, y, w, h){  // 모든 표의 머리글 아이콘(종류·정렬 표시)은 숨김
    if (arguments.length >= 5 && y >= -2 && y < 40 && w <= 28 && h <= 28 && inGrid(this.canvas)){ return; }
    return di.apply(this, arguments);
  };
  // 2026-11-10 표에서 칸을 누르면 그 줄 전체를 옅게 표시 (옆으로 넘겨도 어느 줄인지 보이게)
  var GRID = '[data-testid="stDataFrame"],[data-testid="stDataFrameGlideDataEditor"]';
  var RH = 35, sel = null;
  function place(){
    if (!sel) return;
    var w = sel.wrap, sc = w.querySelector('.dvn-scroller'), cv = w.querySelector('canvas');
    if (!document.body.contains(w) || !sc || !cv){ if (sel.bar) sel.bar.remove(); sel = null; return; }
    var top = RH + sel.row * RH - sc.scrollTop, h = cv.clientHeight;
    var b = sel.bar;
    if (top < RH - 1 || top + RH > h + 1){ b.style.display = 'none'; return; }
    b.style.display = 'block';
    b.style.top = (cv.offsetTop + top) + 'px';
    b.style.left = cv.offsetLeft + 'px';
    b.style.width = cv.clientWidth + 'px';
  }
  document.addEventListener('pointerdown', function(e){
    var wrap = e.target && e.target.closest && e.target.closest(GRID);
    var cv = wrap && wrap.querySelector('canvas');
    if (!wrap){
      if (sel){ sel.bar.remove(); sel = null; }
      return;
    }
    var y = e.clientY - cv.getBoundingClientRect().top;
    if (y < RH) return;  // 머리글
    var sc = wrap.querySelector('.dvn-scroller');
    var row = Math.floor((y - RH + (sc ? sc.scrollTop : 0)) / RH);
    if (sel && sel.wrap !== wrap){ sel.bar.remove(); sel = null; }
    if (!sel){
      var host = cv.parentElement;
      if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
      var b = document.createElement('div');
      b.style.cssText = 'position:absolute;pointer-events:none;height:' + RH + 'px;background:rgba(99,102,241,.22);box-shadow:inset 0 0 0 1px rgba(129,140,248,.7);z-index:2;';
      host.appendChild(b);
      sel = {wrap: wrap, bar: b};
    }
    sel.row = row; place();
  }, true);
  document.addEventListener('scroll', place, true);
  W.addEventListener('resize', place);
  P.fillText = function(t, x, y, mw){
    var r = this.__r;
    if (r && (this.textAlign === 'left' || this.textAlign === 'start' || this.textAlign === 'right') && x >= r[0] - 1 && x <= r[0] + r[2] && inGrid(this.canvas) && this.measureText(t).width <= r[2] - 20){
      this.textAlign = 'center';
      ft.call(this, t, r[0] + r[2] / 2, y);
      this.textAlign = 'start';
      return;
    }
    return ft.apply(this, arguments);
  };
})();
"""


def inject():
    import streamlit as st
    st.html("<script>" + RUNTIME_JS + "</script>", unsafe_allow_javascript=True)
