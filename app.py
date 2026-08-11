import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Saturday Bonus OT Calculator", layout="wide")

st.title("Overtime Rate Calculator")
st.caption("Saturday bonus adjustment for overtime pay. Weeks run Sunday through Saturday. "
           "Your file is processed entirely in this browser tab - nothing is uploaded to any server.")

# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------
with st.sidebar:
    st.header("Settings")
    SAT_RATE = st.number_input("Saturday bonus ($ per qualifying Saturday)",
                               min_value=0.0, value=30.0, step=5.0)
    MIN_SAT_HOURS = st.number_input("Minimum Saturday hours to qualify",
                                    min_value=0.0, value=6.0, step=0.5)
    st.markdown("---")
    st.markdown("**Accepted CSV layouts**")
    st.markdown("**Grid:** first column is the employee name, then one column per "
                "date (the header is the date), cells are hours like 8:26 or 8.43.")
    st.markdown("**List:** three columns named Employee, Date, Hours.")
    sample_csv = ("Employee,07/12/2026,07/13/2026,07/18/2026,07/19/2026,07/20/2026,07/25/2026\n"
                  "JANE DOE,0:00,8:26,7:15,0:00,9:12,6:30\n"
                  "JOHN SMITH,4:00,9:41,0:00,0:00,10:05,0:00\n")
    st.download_button("Download sample CSV", sample_csv, "sample_time.csv", "text/csv")

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def parse_duration(v):
    """Hours as float from '8:26', '08:26:00', '8.43', or blank."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60.0
        if len(parts) == 3:
            return int(parts[0]) + int(parts[1]) / 60.0 + int(parts[2]) / 3600.0
    except ValueError:
        return 0.0
    return 0.0


def fmt_hm(hours):
    """43.6667 -> '43:40'"""
    total_min = int(round(hours * 60))
    return "{0}:{1:02d}".format(total_min // 60, total_min % 60)


def week_start_of(d):
    """Sunday that starts the week containing d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def load_csv(uploaded):
    """Return long dataframe: employee | date | hours. Raises ValueError on failure."""
    raw = pd.read_csv(uploaded, dtype=str)
    raw.columns = [str(c).strip() for c in raw.columns]

    # Which headers are dates?
    date_cols = {}
    for c in raw.columns:
        ts = pd.to_datetime(c, errors="coerce")
        if pd.notna(ts):
            date_cols[c] = ts.date()

    if len(date_cols) >= 2:
        # ---- Grid layout ----
        name_col = None
        for c in raw.columns:
            if c not in date_cols:
                name_col = c
                break
        if name_col is None:
            raise ValueError("Grid layout found, but no employee-name column.")
        rows = []
        for _, r in raw.iterrows():
            name = str(r[name_col]).strip() if pd.notna(r[name_col]) else ""
            if not name or name.lower() in ("nan", "total", "totals"):
                continue
            for c, d in date_cols.items():
                h = parse_duration(r[c])
                if h > 0:
                    rows.append((name, d, h))
        if not rows:
            raise ValueError("No time entries found in the file.")
        return pd.DataFrame(rows, columns=["employee", "date", "hours"])

    # ---- List layout ----
    def find_col(options):
        for c in raw.columns:
            if c.lower() in options:
                return c
        return None

    emp_c = find_col(("employee", "name", "employee name"))
    date_c = find_col(("date", "day", "work date"))
    hrs_c = find_col(("hours", "duration", "time", "hrs"))
    if not (emp_c and date_c and hrs_c):
        raise ValueError("Could not recognize the layout. Use the Grid layout "
                         "(employee column + date columns) or a List with "
                         "Employee, Date, Hours columns.")
    out = pd.DataFrame({
        "employee": raw[emp_c].astype(str).str.strip(),
        "date": pd.to_datetime(raw[date_c], errors="coerce").dt.date,
        "hours": raw[hrs_c].map(parse_duration),
    })
    out = out[(out["employee"] != "") & out["date"].notna() & (out["hours"] > 0)]
    if out.empty:
        raise ValueError("No usable time entries found in the file.")
    return out


# ---------------------------------------------------------------
# Upload
# ---------------------------------------------------------------
uploaded = st.file_uploader("Upload the time CSV", type=["csv"])
if uploaded is None:
    st.info("Upload a CSV of time entries to begin. A sample file showing the "
            "expected layout is in the sidebar.")
    st.stop()

try:
    data = load_csv(uploaded)
except ValueError as e:
    st.error(str(e))
    st.stop()

data_min, data_max = data["date"].min(), data["date"].max()

# ---------------------------------------------------------------
# Date range
# ---------------------------------------------------------------
def last_two_weeks():
    today = date.today()
    days_since_sat = (today.weekday() - 5) % 7
    if days_since_sat == 0:
        days_since_sat = 7
    end = today - timedelta(days=days_since_sat)   # most recent completed Saturday
    return end - timedelta(days=13), end


if "start_d" not in st.session_state:
    st.session_state.start_d = week_start_of(data_min)
    st.session_state.end_d = week_start_of(data_max) + timedelta(days=6)


def set_last2():
    s, e = last_two_weeks()
    st.session_state.start_d = s
    st.session_state.end_d = e


c1, c2, c3 = st.columns([2, 2, 1])
c1.date_input("Start date", key="start_d")
c2.date_input("End date", key="end_d")
c3.markdown("&nbsp;")
c3.button("Last 2 Weeks", on_click=set_last2)

start_d, end_d = st.session_state.start_d, st.session_state.end_d
if start_d > end_d:
    st.error("Start date is after end date.")
    st.stop()

mask = (data["date"] >= start_d) & (data["date"] <= end_d)
period = data[mask].copy()
if period.empty:
    st.warning("No time entries between {0} and {1}. The file covers {2} to {3}.".format(
        start_d, end_d, data_min, data_max))
    st.stop()

if start_d.weekday() != 6 or end_d.weekday() != 5:
    st.caption("Note: the selected range does not start on a Sunday / end on a "
               "Saturday, so the first or last week may be partial.")

# ---------------------------------------------------------------
# Weekly calculations
# ---------------------------------------------------------------
period["week_start"] = period["date"].map(week_start_of)

week_rows = []
for (emp, ws), grp in period.groupby(["employee", "week_start"]):
    total = grp["hours"].sum()
    ot = max(0.0, total - 40.0)
    reg = total - ot
    sat_day_hours = grp[grp["date"].map(lambda d: d.weekday() == 5)].groupby("date")["hours"].sum()
    sat_count = int((sat_day_hours >= MIN_SAT_HOURS).sum()) if len(sat_day_hours) else 0
    bonus = sat_count * SAT_RATE
    bonus_hr = (bonus / total) if (ot > 0 and total > 0) else 0.0
    week_rows.append({
        "employee": emp, "week_start": ws, "total": total, "reg": reg, "ot": ot,
        "sat_count": sat_count, "bonus": bonus, "bonus_hr": bonus_hr,
        "flag": (ot > 0 and bonus > 0),
    })
weeks = pd.DataFrame(week_rows)

# Per-employee summary
emp_rows = []
for emp, grp in weeks.groupby("employee"):
    ot_weeks = grp[grp["ot"] > 0]
    best_bhr, best_week = 0.0, None
    if not ot_weeks.empty:
        idx = ot_weeks["bonus_hr"].idxmax()
        best_bhr = ot_weeks.loc[idx, "bonus_hr"]
        best_week = ot_weeks.loc[idx, "week_start"]
    emp_rows.append({
        "employee": emp,
        "total": grp["total"].sum(),
        "ot": grp["ot"].sum(),
        "bonus": grp["bonus"].sum(),
        "best_bhr": best_bhr,
        "best_week": best_week,
    })
summary = pd.DataFrame(emp_rows).sort_values("employee").reset_index(drop=True)

# ---------------------------------------------------------------
# One-table view: enter wages, see OT rates
# ---------------------------------------------------------------
st.subheader("Employees")

if "wages" not in st.session_state:
    st.session_state.wages = {}

# Build the editor table. Employees with overtime get a red flag in the name
# column so it's obvious which rows need a wage.
def _label(emp, has_ot):
    return ("\u26A0 " + emp) if has_ot else emp   # warning sign for OT

editor_in = pd.DataFrame({
    "Employee": [_label(r["employee"], r["ot"] > 0) for _, r in summary.iterrows()],
    "Regular": [fmt_hm(v) for v in summary["total"] - summary["ot"]],
    "Overtime": [fmt_hm(v) if v > 0 else "-" for v in summary["ot"]],
    "Sat Bonus": ["${0:,.2f}".format(v) for v in summary["bonus"]],
    "Hourly Rate": [
        st.session_state.wages.get(e) if o > 0 else None
        for e, o in zip(summary["employee"], summary["ot"])
    ],
    "OT Rate": [""] * len(summary),
})

edited = st.data_editor(
    editor_in,
    hide_index=True,
    disabled=["Employee", "Regular", "Overtime", "Sat Bonus", "OT Rate"],
    column_config={
        "Hourly Rate": st.column_config.NumberColumn(
            "Hourly Rate ($/hr)",
            help="Enter for employees marked with the warning sign.",
            min_value=0.0, step=0.25, format="$%.2f",
        ),
        "OT Rate": st.column_config.TextColumn(
            "OT Rate ($/hr)",
            help="(hourly rate + highest Bonus/Hr among OT weeks) x 1.5",
        ),
    },
    key="main_editor",
    use_container_width=True,
)

# Persist wages + compute OT rates, then re-display the OT Rate column filled in.
ot_rate_lookup = {}
for i, r in summary.iterrows():
    emp = r["employee"]
    wage_in = edited.iloc[i]["Hourly Rate"]
    if r["ot"] > 0 and pd.notna(wage_in):
        st.session_state.wages[emp] = float(wage_in)
        rate = (float(wage_in) + r["best_bhr"]) * 1.5
        ot_rate_lookup[emp] = rate

# Show a second, read-only table with the computed OT rates for overtime employees.
ot_only = summary[summary["ot"] > 0]
if not ot_only.empty:
    st.markdown("**Overtime rates**")
    ot_view = pd.DataFrame({
        "Employee": ot_only["employee"].values,
        "Hourly Rate": [
            "${0:,.2f}".format(st.session_state.wages[e])
            if e in st.session_state.wages else "enter above"
            for e in ot_only["employee"]
        ],
        "OT Rate": [
            "${0:,.2f}".format(ot_rate_lookup[e])
            if e in ot_rate_lookup else "-"
            for e in ot_only["employee"]
        ],
    })
    st.dataframe(ot_view, hide_index=True, use_container_width=True)
    st.caption("\u26A0 marks employees with overtime. "
               "OT Rate = (hourly rate + highest Bonus/Hr among OT weeks) x 1.5")
else:
    st.success("No employee has overtime in this period.")

# ---------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------
st.subheader("Export")

wage_map = st.session_state.get("wages", {})
export = pd.DataFrame({
    "Employee": summary["employee"].values,
    "Regular Hours": (summary["total"] - summary["ot"]).round(4).values,
    "Overtime Hours": summary["ot"].round(4).values,
    "Saturday Bonus $": summary["bonus"].round(2).values,
    "Hourly Rate": [
        wage_map.get(e) if o > 0 else None
        for e, o in zip(summary["employee"], summary["ot"])
    ],
    "OT Rate": [
        round((wage_map[e] + b) * 1.5, 4) if (e in wage_map and o > 0) else None
        for e, b, o in zip(summary["employee"], summary["best_bhr"], summary["ot"])
    ],
})

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as xw:
    export.to_excel(xw, sheet_name="OT Report", index=False)

st.download_button(
    "Download Excel report",
    buf.getvalue(),
    file_name="OT_Report_{0}_to_{1}.xlsx".format(start_d, end_d),
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
