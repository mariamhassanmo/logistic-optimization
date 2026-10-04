"""Streamlit demo for Logistics Optimization V2.   Run:  streamlit run app.py

This file is presentation only. All logic lives in ui_service.py and the existing
optimizer / scheduler / routing / inventory modules.
"""
from __future__ import annotations

from datetime import date, datetime, time

import streamlit as st

import ui_data
import ui_service
from config import TIMEZONE, TIMEZONE_NAME

st.set_page_config(page_title="Logistics Optimizer V2", page_icon="🚚", layout="wide")



if "customer_city" not in st.session_state:
       st.session_state.update(customer_city="Cairo", sku="IPHONE17-256-BLK", qty=1,
                               order_date=date(2026, 10, 5), order_time=time(14, 0))

st.title("🚚 Logistics Optimizer")

gi


# ---------------------------------------------------------------- 1. order input
st.subheader("1 · Order")
c1, c2, c3, c4, c5 = st.columns([2, 3, 1, 2, 2])
city = c1.selectbox("Customer location", list(ui_data.CITIES), key="customer_city")
sku = c2.selectbox("Product", list(ui_data.PRODUCTS), format_func=ui_data.PRODUCTS.get, key="sku")
qty = c3.number_input("Qty", min_value=1, max_value=10, step=1, key="qty")
order_date = c4.date_input("Order date", key="order_date")
order_time = c5.time_input(f"Order time ({TIMEZONE_NAME})", step=300, key="order_time")
now = datetime.combine(order_date, order_time, tzinfo=TIMEZONE)

analysis = ui_service.analyze(city, sku, int(qty), now)

# ---------------------------------------------------------------- 2. companies table
st.subheader("2 · Logistics companies")


def highlight(row):
    if str(row["Status"]).startswith("✅"):
        return ["background-color: rgba(46, 160, 67, 0.20); font-weight: 600"] * len(row)
    if str(row["Status"]).startswith("Excluded"):
        return ["opacity: 0.55"] * len(row)
    return [""] * len(row)


st.dataframe(
    analysis.table.style.apply(highlight, axis=1), hide_index=True,
    column_config={
        "Waiting (h)": st.column_config.NumberColumn(format="%.1f"),
        "Distance (km)": st.column_config.NumberColumn(format="%.0f"),
        "Travel time (h)": st.column_config.NumberColumn(format="%.1f"),
        "Total expected (h)": st.column_config.NumberColumn(format="%.1f"),
    })
st.caption("Excluded companies are removed before any time comparison. Total = waiting + travel.")

# ---------------------------------------------------------------- 3. recommendation
st.subheader("3 · Recommendation")
if analysis.selected:
    best = analysis.selected
    st.success(f"**{best.company_name}** ({analysis.selected_city}) - ships from warehouse {best.warehouse_id}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total expected delivery time", ui_service.fmt_hours(best.total_hours))
    m2.metric("Road distance", f"{best.distance_km:.0f} km")
    m3.metric("Waiting + travel", f"{best.waiting_hours:.1f} h + {best.travel_hours:.1f} h")
    st.write("**Why this company?**")
    for line in analysis.result.explanation:
        st.markdown(f"- {line}")
    with st.expander("Waiting vs travel time per valid company"):
        st.bar_chart(analysis.chart_frame(), horizontal=True)
else:
    st.error(analysis.error)

st.caption("Demo data is illustrative. Road distances come from an offline approximate road-km model "
           "(avg 80 km/h + 15 min city overhead, no traffic). The same optimizer runs with live "
           "openrouteservice routing via `main.py`.")
