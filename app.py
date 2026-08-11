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
# Wage entry for overtime employees  (the dynamic part)
# ---------------------------------------------------------------
ot_emps = summary[summary["ot"] > 0].copy()

st.subheader("Overtime employees - enter base hourly wage")
if ot_emps.empty:
    st.success("No employee has overtime in this period.")
else:
    if "wages" not in st.session_state:
        st.session_state.wages = {}

    editor_in = pd.DataFrame({
        "Employee": ot_emps["employee"].values,
        "OT Hours": [fmt_hm(h) for h in ot_emps["ot"]],
        "Highest Bonus/Hr": ot_emps["best_bhr"].round(4).values,
        "Base Wage": [st.session_state.wages.get(e) for e in ot_emps["employee"]],
    })
    edited = st.data_editor(
        editor_in,
        hide_index=True,
        disabled=["Employee", "OT Hours", "Highest Bonus/Hr"],
        column_config={
            "Base Wage": st.column_config.NumberColumn("Base Wage ($/hr)",
                                                       min_value=0.0, step=0.25,
                                                       format="$%.2f"),
            "Highest Bonus/Hr": st.column_config.NumberColumn(format="$%.4f"),
        },
        key="wage_editor",
    )

    # persist wages + compute OT rates
    results = []
    for _, r in edited.iterrows():
        w = r["Base Wage"]
        if pd.notna(w):
            st.session_state.wages[r["Employee"]] = float(w)
        bhr = float(r["Highest Bonus/Hr"])
        ot_rate = (float(w) + bhr) * 1.5 if pd.notna(w) else None
        results.append({"Employee": r["Employee"],
                        "Base Wage": w,
                        "Bonus/Hr Used": bhr,
                        "OT Rate": ot_rate})
    res_df = pd.DataFrame(results)

    st.subheader("Overtime rates")
    show = res_df.copy()
    show["Base Wage"] = show["Base Wage"].map(lambda v: "${0:,.2f}".format(v) if pd.notna(v) else "-")
    show["Bonus/Hr Used"] = show["Bonus/Hr Used"].map(lambda v: "${0:,.4f}".format(v))
    show["OT Rate"] = show["OT Rate"].map(lambda v: "${0:,.2f}".format(v) if v is not None else "enter wage")
    st.dataframe(show, hide_index=True, use_container_width=True)
    st.caption("OT Rate = (base wage + highest Bonus/Hr among overtime weeks) x 1.5")

# ---------------------------------------------------------------
# Week-by-week detail
# ---------------------------------------------------------------
st.subheader("Week-by-week detail")
best_lookup = {r["employee"]: r["best_week"] for _, r in summary.iterrows()}

for emp in summary["employee"]:
    grp = weeks[weeks["employee"] == emp].sort_values("week_start")
    label = "{0}  -  {1} total".format(emp, fmt_hm(grp["total"].sum()))
    if (grp["ot"] > 0).any():
        label += "  -  OT " + fmt_hm(grp["ot"].sum())
    with st.expander(label):
        det = pd.DataFrame({
            "Week": [
                "{0}{1} - {2}".format(
                    "* " if (best_lookup.get(emp) == ws and (grp[grp["week_start"] == ws]["ot"] > 0).any()) else "",
                    ws.strftime("%b %d"),
                    (ws + timedelta(days=6)).strftime("%b %d"))
                for ws in grp["week_start"]],
            "Total": [fmt_hm(v) for v in grp["total"]],
            "Regular": [fmt_hm(v) for v in grp["reg"]],
            "Overtime": [fmt_hm(v) for v in grp["ot"]],
            "Sat Bonus": ["${0:,.2f}".format(v) for v in grp["bonus"]],
            "Bonus/Hr": ["${0:,.4f}".format(v) if v > 0 else "-" for v in grp["bonus_hr"]],
            "OT + Sat": ["YES" if f else "" for f in grp["flag"]],
        })

        def _highlight(row):
            style = "color: #cc0000; font-weight: 600" if row["OT + Sat"] == "YES" else ""
            return [style] * len(row)

        st.dataframe(det.style.apply(_highlight, axis=1), hide_index=True,
                     use_container_width=True)
st.caption("* marks the week whose Bonus/Hr sets the overtime rate. "
           "Red rows have both overtime and a qualifying Saturday.")

# ---------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------
st.subheader("Export")

sum_out = summary.copy()
sum_out["best_week"] = sum_out["best_week"].map(lambda v: str(v) if v is not None else "")
sum_out.columns = ["Employee", "Total Hours", "OT Hours", "Sat Bonus $",
                   "Highest Bonus/Hr", "Week Used"]
if not ot_emps.empty:
    wage_map = st.session_state.get("wages", {})
    sum_out["Base Wage"] = sum_out["Employee"].map(lambda e: wage_map.get(e))
    sum_out["OT Rate"] = [
        (wage_map[e] + b) * 1.5 if (e in wage_map and o > 0) else None
        for e, b, o in zip(sum_out["Employee"], sum_out["Highest Bonus/Hr"],
                           sum_out["OT Hours"])]

wk_out = weeks.copy().sort_values(["employee", "week_start"])
wk_out["week_start"] = wk_out["week_start"].map(str)
wk_out.columns = ["Employee", "Week Starting", "Total Hours", "Regular Hours",
                  "OT Hours", "Qualifying Saturdays", "Sat Bonus $", "Bonus/Hr",
                  "OT + Sat Week"]

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as xw:
    sum_out.to_excel(xw, sheet_name="Summary", index=False)
    wk_out.to_excel(xw, sheet_name="Weekly Detail", index=False)

st.download_button(
    "Download Excel report",
    buf.getvalue(),
    file_name="OT_Report_{0}_to_{1}.xlsx".format(start_d, end_d),
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
