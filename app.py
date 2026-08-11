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
# The payroll table
#
# One table, laid out in QuickBooks entry order:
#   Employee | Regular | Overtime | Sat Bonus | Hourly Rate (input) | OT Rate
#
# Trick for same-table refresh: read this run's pending edits out of the
# editor's widget state BEFORE building the table, so the OT Rate column is
# already up to date when the table renders. Tab out of a wage cell and the
# rate appears on the same row.
# ---------------------------------------------------------------
st.subheader("Payroll entry")

if "wages" not in st.session_state:
    st.session_state.wages = {}

with st.sidebar:
    st.markdown("---")
    hours_fmt = st.radio("Show hours as", ["H:MM", "Decimal"], horizontal=True)

def show_hours(v):
    if v <= 0:
        return ""
    return fmt_hm(v) if hours_fmt == "H:MM" else "{0:.2f}".format(v)

# Stable row order; key changes whenever the employee set changes so stale
# row-indexed edits can never land on the wrong person.
emps = list(summary["employee"])
editor_key = "payroll_editor_{0}".format(abs(hash(tuple(emps))) % 10**8)

# 1. Pull pending edits (this run's keystrokes) into the wages dict first.
pending = st.session_state.get(editor_key, {}).get("edited_rows", {})
for row_idx, changes in pending.items():
    if "Hourly Rate" in changes:
        emp = emps[int(row_idx)]
        val = changes["Hourly Rate"]
        if val is None:
            st.session_state.wages.pop(emp, None)
        else:
            st.session_state.wages[emp] = float(val)

# 2. Build the table with OT Rate already computed from current wages.
def ot_rate_for(emp, ot, best_bhr):
    if ot <= 0:
        return ""
    w = st.session_state.wages.get(emp)
    if w is None:
        return "\u26A0 enter rate"
    return "${0:,.2f}".format((w + best_bhr) * 1.5)

table = pd.DataFrame({
    "Employee": emps,
    "Regular": [show_hours(t - o) for t, o in zip(summary["total"], summary["ot"])],
    "Overtime": [show_hours(o) for o in summary["ot"]],
    "Sat Bonus": [("${0:,.2f}".format(b) if b > 0 else "") for b in summary["bonus"]],
    "Hourly Rate": [
        st.session_state.wages.get(e) if o > 0 else None
        for e, o in zip(summary["employee"], summary["ot"])
    ],
    "OT Rate": [
        ot_rate_for(e, o, b)
        for e, o, b in zip(summary["employee"], summary["ot"], summary["best_bhr"])
    ],
})

st.data_editor(
    table,
    hide_index=True,
    disabled=["Employee", "Regular", "Overtime", "Sat Bonus", "OT Rate"],
    column_config={
        "Regular": st.column_config.TextColumn("Regular", width="small"),
        "Overtime": st.column_config.TextColumn("Overtime", width="small"),
        "Sat Bonus": st.column_config.TextColumn("Sat Bonus", width="small"),
        "Hourly Rate": st.column_config.NumberColumn(
            "Hourly Rate ($/hr)",
            help="Only needed where OT Rate says 'enter rate'.",
            min_value=0.0, step=0.25, format="$%.2f", width="small",
        ),
        "OT Rate": st.column_config.TextColumn(
            "OT Rate ($/hr)",
            help="(hourly rate + highest Bonus/Hr among OT weeks) x 1.5",
            width="small",
        ),
    },
    key=editor_key,
    use_container_width=True,
    height=min(38 * (len(table) + 1) + 4, 900),
)

n_ot = int((summary["ot"] > 0).sum())
n_done = sum(1 for e, o in zip(summary["employee"], summary["ot"])
             if o > 0 and e in st.session_state.wages)
if n_ot == 0:
    st.success("No employee has overtime in this period.")
elif n_done < n_ot:
    st.warning("{0} of {1} overtime employees still need an hourly rate "
               "(rows showing \u26A0 enter rate).".format(n_ot - n_done, n_ot))
else:
    st.success("All {0} overtime employees have rates entered.".format(n_ot))
st.caption("Type a rate and press Tab or Enter - the OT Rate fills in on the same row. "
           "OT Rate = (hourly rate + highest Bonus/Hr among overtime weeks) x 1.5")

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
