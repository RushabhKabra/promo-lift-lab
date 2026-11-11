from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.theme import inject  # noqa: E402
from insights.answer import answer_question, insight_cards  # noqa: E402
from insights.retrieve import load_kpis  # noqa: E402

st.set_page_config(page_title="Ask the data · promo-lift lab", layout="wide")
inject()


def _sources(sources: list[dict]) -> None:
    if not sources:
        return
    bits = []
    for source in sources:
        value = source.get("value")
        shown = "—" if value is None else value
        bits.append(f"{source.get('metric')} · {source.get('grain')} · {source.get('period')} · {shown}")
    st.markdown('<p class="source-line">' + "<br>".join(bits) + "</p>", unsafe_allow_html=True)


st.title("Ask the certified tables")
st.write(
    "I answer from the KPI snapshot the warehouse already computed. "
    "If an API key is present I will also ask a model, and it only sees that snapshot plus the glossary. "
    "Without a key, the same cards still show up. Either way the metric, the grain, and the period sit under the reply."
)

try:
    kpis = load_kpis()
except Exception as exc:  # noqa: BLE001
    st.error(f"I could not read the certified snapshot. {exc}")
    st.stop()

st.subheader("What I would put on the table first")
for card in insight_cards(kpis):
    with st.container(border=True):
        st.markdown(f"**{card['question']}**")
        st.write(card["answer"])
        _sources(card.get("sources") or [])

st.subheader("Ask something else")
suggestions = [
    "Which campaigns lost money after discounts?",
    "How did meat do on lift?",
    "Did the forecast beat the four-week mean?",
    "Who is promo-sensitive?",
    "What is the capital of France?",
]
picked = st.pills("A few I have already asked", suggestions) if hasattr(st, "pills") else None
question = st.text_input("Question", value=picked or "")
if st.button("Look it up", type="primary") and question.strip():
    result = answer_question(question.strip(), kpis)
    st.write(result["answer"])
    if result.get("used_llm"):
        st.caption("The wording came back from the model. The sources are still the certified metrics, not the model's memory.")
    elif result.get("refused"):
        st.caption("Refused, because it is outside this lab.")
    else:
        st.caption("Templated from the certified snapshot. No model call.")
    _sources(result.get("sources") or [])
