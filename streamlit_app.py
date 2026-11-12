from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from diagnostic_platform.models import MotorProfile
from diagnostic_platform.sources import SimulatedMotorSource
from diagnostic_platform.storage import DiagnosticStore
from diagnostic_platform.workflow import MotorTestRunner


APP_DIR = Path(__file__).resolve().parent
DATABASE_PATH = APP_DIR / "diagnostics.db"


def default_profile() -> MotorProfile:
    return MotorProfile("MOTOR-001", 12.0, 2.0, 2500.0, 1.2, 3.0, 80.0)


def open_store() -> DiagnosticStore:
    return DiagnosticStore(DATABASE_PATH)


def ensure_default_profile() -> None:
    store = open_store()
    try:
        if not store.list_profiles():
            store.save_profile(default_profile())
    finally:
        store.close()


def condition_badge(condition: str | None) -> str:
    return {"HEALTHY": "🟢 Healthy", "WARNING": "🟠 Warning", "CRITICAL": "🔴 Critical"}.get(
        condition or "", "⚪ Not evaluated"
    )


def dashboard_page() -> None:
    st.title("Adaptive Diagnostic System")
    st.caption("Software-defined motor diagnostics · Simulation mode")
    store = open_store()
    try:
        sessions = store.list_sessions()
    finally:
        store.close()

    total = len(sessions)
    completed = sum(row["state"] == "COMPLETE" for row in sessions)
    warnings = sum(row["condition"] in {"WARNING", "CRITICAL"} for row in sessions)
    c1, c2, c3 = st.columns(3)
    c1.metric("Tests recorded", total)
    c2.metric("Completed", completed)
    c3.metric("Tests needing attention", warnings)

    st.subheader("System status")
    status1, status2, status3 = st.columns(3)
    status1.success("Simulator ready")
    status2.info("STM32 not connected")
    status3.info(f"Database: {DATABASE_PATH.name}")

    st.subheader("Recent tests")
    if not sessions:
        st.info("No tests have been run yet. Open **Run test** to create one.")
        return
    frame = pd.DataFrame([dict(row) for row in sessions[:8]])
    frame["status"] = frame["condition"].apply(condition_badge)
    st.dataframe(
        frame[["id", "device_id", "scenario", "state", "status", "health_score", "sample_count"]],
        hide_index=True,
        width="stretch",
        column_config={"id": "Test", "device_id": "Device", "health_score": "Health"},
    )


def run_test_page() -> None:
    st.title("Run motor diagnostic")
    st.caption("The simulator uses the same measurement boundary planned for the STM32.")
    store = open_store()
    try:
        profiles = store.list_profiles()
    finally:
        store.close()
    if not profiles:
        st.warning("Create a motor profile before running a test.")
        return

    profile_by_id = {p.device_id: p for p in profiles}
    left, right = st.columns(2)
    device_id = left.selectbox("Device profile", list(profile_by_id))
    scenario = right.selectbox(
        "Simulation scenario",
        list(SimulatedMotorSource.SCENARIOS),
        format_func=lambda value: value.replace("_", " ").title(),
    )
    samples = st.slider("Samples", 5, 100, 25, 5)
    sample_delay = st.slider("Display interval (seconds)", 0.0, 0.5, 0.08, 0.02)

    profile = profile_by_id[device_id]
    with st.expander("Profile limits"):
        st.write(
            f"Rated: **{profile.rated_voltage:g} V**, **{profile.rated_current:g} A**, "
            f"**{profile.rated_rpm:g} RPM** · Limits: **{profile.max_current:g} A**, "
            f"**{profile.max_temperature:g} °C**"
        )

    if not st.button("Start diagnostic test", type="primary", width="stretch"):
        st.info("Choose a scenario and start the test. Results will be saved automatically.")
        return

    metrics = st.empty()
    progress = st.progress(0, text="Connecting to simulator…")
    chart = st.empty()
    readings: list[dict[str, float | int | None]] = []

    def update(measurement, report, total_samples: int) -> None:
        readings.append(
            {
                "Sequence": measurement.sequence,
                "Voltage (V)": measurement.voltage,
                "Current (A)": measurement.current,
                "RPM": measurement.rpm,
                "Temperature (°C)": measurement.temperature,
            }
        )
        with metrics.container():
            cols = st.columns(5)
            cols[0].metric("Voltage", "N/A" if measurement.voltage is None else f"{measurement.voltage:.2f} V")
            cols[1].metric("Current", "N/A" if measurement.current is None else f"{measurement.current:.2f} A")
            cols[2].metric("Power", "N/A" if measurement.input_power is None else f"{measurement.input_power:.1f} W")
            cols[3].metric("RPM", "N/A" if measurement.rpm is None else f"{measurement.rpm:.0f}")
            cols[4].metric("Temperature", "N/A" if measurement.temperature is None else f"{measurement.temperature:.1f} °C")
        progress.progress(measurement.sequence / total_samples, text=f"Acquiring sample {measurement.sequence} of {total_samples}")
        frame = pd.DataFrame(readings).set_index("Sequence")
        chart.line_chart(frame, width="stretch")
        if sample_delay:
            time.sleep(sample_delay)

    source = SimulatedMotorSource(profile, scenario, seed=42)
    store = open_store()
    runner = MotorTestRunner(source, store)
    try:
        session_id, report = runner.run(profile, scenario, samples, update)
    except (TimeoutError, RuntimeError) as exc:
        progress.empty()
        st.error(f"Test stopped: {exc}")
        st.warning(f"System state: {runner.state.value}")
        return
    finally:
        store.close()

    progress.progress(1.0, text="Test complete")
    st.subheader(f"Result · {condition_badge(report.condition)}")
    result1, result2 = st.columns(2)
    result1.metric("Motor health", f"{report.health_score}%")
    result2.metric("Saved test", f"#{session_id}")
    for finding in report.findings:
        message = f"**{finding.code}** — {finding.message}"
        if finding.severity.value == "CRITICAL":
            st.error(message)
        elif finding.severity.value == "WARNING":
            st.warning(message)
        else:
            st.success(message)
        if finding.possible_causes:
            st.caption("Possible causes: " + ", ".join(finding.possible_causes))


def history_page() -> None:
    st.title("Test history")
    store = open_store()
    try:
        sessions = store.list_sessions()
        if not sessions:
            st.info("No saved tests yet.")
            return
        labels = {
            f"Test #{row['id']} · {row['device_id']} · {row['scenario']} · {row['state']}": row["id"]
            for row in sessions
        }
        selected = st.selectbox("Saved test", list(labels))
        session_id = labels[selected]
        summary = store.session_summary(session_id)
        measurements = store.session_measurements(session_id)
        findings = store.session_findings(session_id)
    finally:
        store.close()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("State", summary["state"])
    c2.metric("Condition", summary["condition"] or "N/A")
    c3.metric("Health", "N/A" if summary["health_score"] is None else f"{summary['health_score']}%")
    c4.metric("Samples", summary["sample_count"])
    if measurements:
        frame = pd.DataFrame([dict(row) for row in measurements]).set_index("sequence")
        st.line_chart(
            frame[["voltage", "current", "rpm", "temperature"]],
            width="stretch",
        )
        with st.expander("Measurement data"):
            st.dataframe(frame, width="stretch")
    st.subheader("Diagnostic findings")
    if findings:
        st.dataframe(pd.DataFrame([dict(row) for row in findings]), hide_index=True, width="stretch")
    else:
        st.info("This test ended before diagnostic findings were generated.")


def profiles_page() -> None:
    st.title("Device profiles")
    st.caption("Profiles define the expected operating range for each motor.")
    with st.form("profile"):
        device_id = st.text_input("Device ID", "MOTOR-002")
        a, b, c = st.columns(3)
        rated_voltage = a.number_input("Rated voltage (V)", 0.1, 1000.0, 12.0)
        rated_current = b.number_input("Rated current (A)", 0.01, 1000.0, 2.0)
        rated_rpm = c.number_input("Rated RPM", 1.0, 100000.0, 2500.0)
        d, e, f = st.columns(3)
        resistance = d.number_input("Winding resistance (Ω)", 0.001, 10000.0, 1.2)
        max_current = e.number_input("Maximum current (A)", rated_current, 1000.0, 3.0)
        max_temperature = f.number_input("Maximum temperature (°C)", 1.0, 500.0, 80.0)
        submitted = st.form_submit_button("Save profile", type="primary")
    if submitted:
        if not device_id.strip():
            st.error("Device ID is required.")
        else:
            profile = MotorProfile(device_id.strip(), rated_voltage, rated_current, rated_rpm,
                                   resistance, max_current, max_temperature)
            store = open_store()
            try:
                store.save_profile(profile)
            finally:
                store.close()
            st.success(f"Saved profile {profile.device_id}.")

    store = open_store()
    try:
        profiles = store.list_profiles()
    finally:
        store.close()
    if profiles:
        st.dataframe(pd.DataFrame([profile.__dict__ for profile in profiles]), hide_index=True, width="stretch")


def main() -> None:
    st.set_page_config(page_title="Adaptive Diagnostic System", page_icon="⚙️", layout="wide")
    ensure_default_profile()
    st.sidebar.title("ADS")
    st.sidebar.caption("Adaptive Diagnosis System")
    page = st.sidebar.radio("Navigation", ["Dashboard", "Run test", "Test history", "Device profiles"])
    st.sidebar.divider()
    st.sidebar.info("Simulation mode\n\nReal STM32 support will use the same measurement interface.")
    {"Dashboard": dashboard_page, "Run test": run_test_page,
     "Test history": history_page, "Device profiles": profiles_page}[page]()


if __name__ == "__main__":
    main()
