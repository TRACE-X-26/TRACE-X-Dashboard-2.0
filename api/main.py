from __future__ import annotations

import asyncio
import csv
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from diagnostic_platform.automated_engine import AutomatedTestEngine, RunRejected, TERMINAL

from diagnostic_platform.config import Settings
from diagnostic_platform.history import parse_csv
from diagnostic_platform.live import LiveMonitor
from diagnostic_platform.physical_circuits import start_capture, arm_capture, capture_reading
from diagnostic_platform.circuit4 import ASSET_ID as CIRCUIT4_ID, MODEL_VERSION as CIRCUIT4_MODEL, REFERENCES as CIRCUIT4_REFERENCES, circuit4_asset, classify_circuit4
from diagnostic_platform.control import (
    SimulatedMotorController,
    SimulatedMotorSequenceService,
    serialize_control_state,
)
from diagnostic_platform.circuits import CircuitDiagnosticService
from diagnostic_platform.measurements import DataSource, motor_measurement_envelopes
from diagnostic_platform.models import MotorProfile
from diagnostic_platform.motor_health import load_json
from diagnostic_platform.multimeter import SimulatedMultimeter
from diagnostic_platform.sources import SimulatedMotorSource
from diagnostic_platform.storage import DiagnosticStore
from diagnostic_platform.stm32 import DeviceResponseError, SimulatedSTM32Connection
from diagnostic_platform.workflow import MotorTestSession, TestState, TestStoppedError

from .schemas import (
    CircuitRunPayload,
    BranchSelectionPayload,
    CircuitPowerPayload,
    AutomatedRunPayload,
    MotorCommandPayload,
    ProfilePayload,
    STM32CommandPayload,
    TestRequest,
    HistoricalImportPayload,
    PhysicalCircuitAsset,
    PhysicalCircuitStart,
    PhysicalCircuitArm,
)
from .dashboard import mount_dashboard


ROOT = Path(__file__).resolve().parents[1]
settings = Settings.from_environment(ROOT)
logger = logging.getLogger("adaptive_diagnostic_system")
logger.setLevel(getattr(logging, settings.log_level))
DATABASE_PATH = settings.database_path
motor_controller = SimulatedMotorController()
motor_sequence = SimulatedMotorSequenceService(motor_controller)
stm32_connection = SimulatedSTM32Connection(motor_controller)
multimeter = SimulatedMultimeter()
circuit_service = CircuitDiagnosticService()
automated_engine = None

live_monitor = LiveMonitor(os.getenv('ADS_LIVE_SERIAL_PORT', '').strip(), settings.serial_baud,
                           protocol=os.getenv('ADS_LIVE_PROTOCOL', 'passive').strip())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_store() -> DiagnosticStore:
    return DiagnosticStore(DATABASE_PATH)


def record_event(event_type: str, severity: str = "INFO", **details: object) -> None:
    try:
        with open_store() as store:
            store.add_event(now(), event_type, severity, details)
    except Exception:
        logger.exception("Unable to persist system event %s", event_type)


def serialize_row(row) -> dict:
    return dict(row)


def serialize_measurement(measurement) -> dict:
    return {
        "sequence": measurement.sequence,
        "timestamp": measurement.timestamp.isoformat(),
        "voltage": measurement.voltage,
        "current": measurement.current,
        "rpm": measurement.rpm,
        "temperature": measurement.temperature,
        "resistance": measurement.resistance,
        "vibration_rms": measurement.vibration_rms,
        "input_power": measurement.input_power,
    }


def serialize_report(report) -> dict:
    return {
        "device_id": report.device_id,
        "health_score": report.health_score,
        "condition": report.condition,
        "findings": [
            {
                "code": finding.code,
                "severity": finding.severity.value,
                "message": finding.message,
                "possible_causes": list(finding.possible_causes),
            }
            for finding in report.findings
        ],
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    global automated_engine
    store = open_store()
    try:
        if not store.list_profiles():
            store.save_profile(MotorProfile("MOTOR-001", 12, 2, 2500, 1.2, 3, 80))
        if not any(asset['asset_id'] == CIRCUIT4_ID for asset in store.circuit_assets()):
            store.save_circuit_asset(circuit4_asset())
    finally:
        store.close()
    record_event("APPLICATION_STARTED", mode=settings.mode, hardware_control=False)
    automated_engine=AutomatedTestEngine(DATABASE_PATH,
        hardware_profile_path=settings.hardware_profile_path,
        hardware_control_enabled=settings.hardware_control_enabled,
        serial_baud=settings.serial_baud,serial_read_timeout=settings.serial_read_timeout,
        serial_command_timeout=min(settings.serial_command_timeout,.5),
        publish=lambda raw,source: live_monitor.publish_acquisition(raw) if source=='stm32_serial' else None)
    automated_engine.recover()
    stm32_connection.connect()
    # A commissioned command owner must not compete with the passive serial reader.
    sensor_monitor=None
    if os.getenv('ADS_LIVE_PROTOCOL','passive')=='ads_json' and live_monitor.port:
        from diagnostic_platform.sensor_monitor import SensorMonitor
        sensor_monitor=SensorMonitor(automated_engine,live_monitor.port,live_monitor.publish_acquisition,
            DATABASE_PATH.parent/'sensor_csv')
        sensor_monitor.start()
    elif not os.getenv('ADS_AUTOMATION_HARDWARE_PROFILE',''): live_monitor.start()
    try:
        yield
    finally:
        if sensor_monitor:sensor_monitor.close()
        automated_engine.close()
        automated_engine=None
        live_monitor.close()
        stm32_connection.disconnect()


app = FastAPI(
    title="Adaptive Diagnostic System API",
    version="0.6.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": settings.mode,
        "database": DATABASE_PATH.name,
        "hardware_control": automated_engine.hardware_runtime.snapshot()['ready'] if automated_engine else False,
        "hardware_control_enabled": settings.hardware_control_enabled,
        "hardware_preflight": automated_engine.hardware_runtime.snapshot() if automated_engine else None,
        "measurement_source": "SIMULATION",
        "legacy_control_source": "SIMULATION",
        "stm32_connection_source": "SIMULATION",
        "automated_test": automated_engine.snapshot() if automated_engine else None,
        "stm32_connected": stm32_connection.is_connected(),
    }


@app.get('/api/live/status')
def live_status() -> dict:
    return live_monitor.snapshot()


@app.get('/api/live/motor')
def live_motor_measurement() -> dict:
    snapshot = live_monitor.snapshot()
    return {key: snapshot[key] for key in ('hardware_connected', 'motor_sample', 'motor_format', 'channels',
                                          'complete_motor_frames', 'pending_motor_fields', 'warnings', 'error',
                                          'stale', 'diagnosis', 'hardware_control')}


@app.websocket('/ws/live')
async def live_updates(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(live_monitor.snapshot())
            await asyncio.sleep(.25)
    except WebSocketDisconnect:
        return


@app.get("/api/hardware/status")
def hardware_status() -> dict:
    return stm32_connection.status()


@app.get("/api/hardware/capabilities")
def hardware_capabilities() -> dict:
    capabilities = stm32_connection.capabilities()
    return {
        "device_id": capabilities.device_id,
        "measurement_types": list(capabilities.measurement_types),
        "commands": list(capabilities.commands),
        "firmware_version": capabilities.firmware_version,
        "source": "SIMULATION",
        "hardware_verified": False,
    }


@app.get("/api/hardware/measurements")
def hardware_measurements() -> dict:
    return stm32_connection.read_measurements()


@app.post("/api/hardware/commands")
def hardware_command(payload: STM32CommandPayload) -> dict:
    try:
        result = stm32_connection.execute(payload.command, payload.arguments)
    except (ValueError, DeviceResponseError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_event(
        "STM32_SIMULATION_COMMAND",
        command=payload.command,
        arguments=payload.arguments,
        source="SIMULATION",
    )
    return {"result": result, "source": "SIMULATION", "hardware_control": False}


@app.get("/api/motor/status")
def motor_status() -> dict:
    state = motor_controller.snapshot()
    telemetry = motor_controller.telemetry()
    return {
        "state": serialize_control_state(state),
        "telemetry": telemetry.__dict__,
        "mode": "simulation",
        "runtime_mode": settings.mode,
        "source": "SIMULATION",
        "sequence": motor_sequence.status().__dict__,
    }


@app.post("/api/motor/commands")
def motor_command(payload: MotorCommandPayload) -> dict:
    active=automated_engine.snapshot() if automated_engine else None
    if active and active['state'] not in TERMINAL:
        if payload.action in {'disable','emergency_stop'}:
            automated_engine.stop(payload.action=='emergency_stop')
        elif active['mode']=='hardware':
            raise HTTPException(status_code=409,detail='A physical automated run owns motor controls')
    if payload.action in {"disable", "emergency_stop"} and motor_sequence.status().running:
        motor_sequence.cancel()
    acknowledgment = motor_controller.command(
        payload.command_id, payload.action, payload.value
    )
    record_event(
        "MOTOR_COMMAND",
        "INFO" if acknowledgment.accepted else "WARNING",
        command_id=payload.command_id,
        action=payload.action,
        value=payload.value,
        accepted=acknowledgment.accepted,
        message=acknowledgment.message,
        source="SIMULATION",
    )
    return {
        "command_id": acknowledgment.command_id,
        "accepted": acknowledgment.accepted,
        "message": acknowledgment.message,
        "state": serialize_control_state(acknowledgment.state),
    }


@app.post("/api/motor/sequences/pwm-ramp")
def start_motor_sequence() -> dict:
    accepted, message = motor_sequence.start()
    logger.info("simulation_sequence_start accepted=%s message=%s", accepted, message)
    record_event("MOTOR_SEQUENCE_STARTED", "INFO" if accepted else "WARNING", accepted=accepted, message=message, source="SIMULATION")
    return {"accepted": accepted, "message": message, "sequence": motor_sequence.status().__dict__}


@app.post("/api/motor/sequences/cancel")
def cancel_motor_sequence() -> dict:
    accepted, message = motor_sequence.cancel()
    logger.info("simulation_sequence_cancel was_running=%s", accepted)
    record_event("MOTOR_SEQUENCE_CANCELLED", was_running=accepted, message=message, source="SIMULATION")
    return {"accepted": accepted, "message": message, "sequence": motor_sequence.status().__dict__}


@app.get("/api/multimeter/readings")
def multimeter_readings() -> dict:
    state = motor_controller.snapshot()
    return multimeter.read(state, motor_controller.telemetry())


@app.get("/api/circuits/profiles")
def circuit_profiles() -> dict:
    return {
        "profiles": circuit_service.list_profiles(),
        "scenarios": list(circuit_service.SCENARIOS),
    }


@app.post("/api/circuits/run")
def run_circuit_test(payload: CircuitRunPayload) -> dict:
    try:
        report=circuit_service.run(payload.profile_id, payload.mode, payload.scenario)
        return test_engine().store.create_simulated_circuit(report)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/api/circuits/assets')
def physical_circuit_assets() -> list[dict]:
    with open_store() as store:
        return store.circuit_assets()


@app.post('/api/circuits/assets', status_code=201)
def save_physical_circuit_asset(payload: PhysicalCircuitAsset) -> dict:
    if payload.asset_id == CIRCUIT4_ID:
        raise HTTPException(status_code=409, detail='Circuit 4 is a versioned preset. Use a different asset ID for modified circuits.')
    asset = payload.model_dump()
    with open_store() as store:
        store.save_circuit_asset(asset)
    return asset


@app.get('/api/circuits/circuit4/reference-analysis')
def circuit4_reference_analysis() -> dict:
    return {'source': 'USER_REPORTED_MULTIMETER_REFERENCE', 'hardware_control': False,
            'cases': [{'label': label, 'voltages': values,
                       'diagnostic': classify_circuit4([{'point_id': point, 'channel': 'test_point_voltage', 'measured': value}
                                                       for point, value in values.items()])}
                      for label, values in CIRCUIT4_REFERENCES.items()]}


@app.get('/api/circuits/captures')
def physical_circuit_history() -> list[dict]:
    with open_store() as store:
        return store.circuit_capture_history()


@app.post('/api/circuits/captures', status_code=201)
def start_physical_circuit(payload: PhysicalCircuitStart) -> dict:
    with open_store() as store:
        asset = next((a for a in store.circuit_assets() if a['asset_id'] == payload.asset_id), None)
        if asset is None:
            raise HTTPException(status_code=404, detail='Circuit asset not found')
        if asset.get('diagnostic_model') == CIRCUIT4_MODEL and not payload.conditions_confirmed:
            raise HTTPException(status_code=409, detail='Confirm that supply, RV1 and fault switches will stay unchanged across TP0–TP4 capture')
        session = start_capture(asset)
        session['conditions_confirmed'] = payload.conditions_confirmed
        return store.create_circuit_capture(session)


@app.post('/api/circuits/captures/{session_id}/arm')
def arm_physical_circuit(session_id: int, payload: PhysicalCircuitArm) -> dict:
    with open_store() as store:
        try:
            return store.update_circuit_capture(arm_capture(store.circuit_capture(session_id), payload.point_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail='Circuit test not found') from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post('/api/circuits/captures/{session_id}/capture')
def capture_physical_circuit(session_id: int) -> dict:
    with open_store() as store:
        try:
            session = capture_reading(store.circuit_capture(session_id), live_monitor.snapshot())
            return store.update_circuit_capture(session)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail='Circuit test not found') from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/scenarios")
def scenarios() -> list[str]:
    return [name for name in SimulatedMotorSource.SCENARIOS if name != "overheating"]


@app.get("/api/baselines")
def list_baselines() -> list[dict]:
    with open_store() as store:
        return [baseline.__dict__ for baseline in store.list_baselines()]


@app.get("/api/profiles")
def list_profiles() -> list[dict]:
    store = open_store()
    try:
        return [profile.__dict__ for profile in store.list_profiles()]
    finally:
        store.close()


@app.post("/api/profiles", status_code=201)
def save_profile(payload: ProfilePayload) -> dict:
    profile = MotorProfile(**payload.model_dump())
    store = open_store()
    try:
        store.save_profile(profile)
    finally:
        store.close()
    return profile.__dict__


@app.get("/api/sessions")
def list_sessions(limit: int = 100) -> list[dict]:
    store = open_store()
    try:
        return [serialize_row(row) for row in store.list_sessions(max(1, min(limit, 500)))]
    finally:
        store.close()


@app.get("/api/events")
def list_events(limit: int = 100) -> list[dict]:
    with open_store() as store:
        return store.list_events(max(1, min(limit, 500)))


@app.get("/api/recordings")
def list_recordings() -> list[dict]:
    with open_store() as store:
        return store.list_recordings()


@app.get("/api/recordings/motor-health-replay")
def motor_health_replay() -> dict:
    path = ROOT / 'reference_data/archive_replay.json'
    if not path.is_file():
        path = ROOT / 'data/archive_replay.json'
    audited = Path(os.getenv('ADS_MOTOR_DATA_DIR', str(ROOT / 'data/motor_audit'))) / 'archive_replay.json'
    if audited.is_file():
        path = audited
    try:
        return load_json(path)
    except FileNotFoundError:
        return {'test_catalog': {}, 'runs': {}}
    except ValueError as exc:
        raise HTTPException(status_code=500, detail='Motor health replay is invalid') from exc


@app.post("/api/recordings", status_code=201)
def import_recording(payload: HistoricalImportPayload) -> dict:
    metadata = payload.model_dump(exclude={"content"})
    try:
        result = parse_csv(payload.content, metadata)
    except (ValueError, TypeError, AttributeError, csv.Error) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with open_store() as store:
        recording_id = store.save_recording(payload.content, result, now())
        return store.recording(recording_id)


@app.get("/api/recordings/{recording_id}")
def get_recording(recording_id: int) -> dict:
    with open_store() as store:
        try:
            return store.recording(recording_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Recording not found") from exc


@app.get("/api/sessions/{session_id}")
def get_session(session_id: int) -> dict:
    store = open_store()
    try:
        try:
            summary = serialize_row(store.session_summary(session_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Test session not found") from exc
        return {
            "summary": summary,
            "measurements": [serialize_row(row) for row in store.session_measurements(session_id)],
            "findings": [serialize_row(row) for row in store.session_findings(session_id)],
        }
    finally:
        store.close()


@app.post("/api/sessions/{session_id}/baseline", status_code=201)
def create_baseline(session_id: int) -> dict:
    with open_store() as store:
        try:
            baseline = store.create_baseline(session_id, now())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Test session not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return baseline.__dict__


@app.websocket("/ws/tests")
async def run_test(websocket: WebSocket) -> None:
    await websocket.accept()
    store: DiagnosticStore | None = None
    session: MotorTestSession | None = None
    try:
        request = TestRequest.model_validate(await websocket.receive_json())
        if request.scenario not in SimulatedMotorSource.SCENARIOS:
            await websocket.send_json({"type": "error", "message": "Unknown simulation scenario"})
            await websocket.close(code=1008)
            return
        store = open_store()
        try:
            profile = store.get_profile(request.device_id)
        except KeyError:
            await websocket.send_json({"type": "error", "message": "Device profile not found"})
            await websocket.close(code=1008)
            return

        source = SimulatedMotorSource(profile, request.scenario, seed=42)
        session = MotorTestSession(source, store)
        session_id = session.start(profile, request.scenario)
        await websocket.send_json(
            {"type": "started", "session_id": session_id, "total_samples": request.samples}
        )
        for _ in range(request.samples):
            sample = session.acquire()
            envelopes = motor_measurement_envelopes(
                sample.measurement,
                device_id=profile.device_id,
                source=DataSource.SIMULATION,
                session_id=session_id,
            )
            await websocket.send_json(
                {
                    "type": "measurement",
                    "measurement": serialize_measurement(sample.measurement),
                    "measurement_envelopes": [item.to_dict() for item in envelopes],
                    "report": serialize_report(sample.report),
                    "source": DataSource.SIMULATION.value,
                }
            )
            session.enforce_safety(sample)
            if request.interval_ms:
                await asyncio.sleep(request.interval_ms / 1000)

        final_report = session.complete()
        await websocket.send_json(
            {"type": "completed", "session_id": session_id, "report": serialize_report(final_report)}
        )
    except TestStoppedError as exc:
        await websocket.send_json(
            {
                "type": "failed",
                "state": exc.state.value,
                "message": str(exc),
                "report": serialize_report(exc.sample.report),
            }
        )
    except TimeoutError as exc:
        await websocket.send_json(
            {"type": "failed", "state": "COMMUNICATION_FAULT", "message": str(exc)}
        )
    except WebSocketDisconnect:
        if session is not None and session.state not in {TestState.COMPLETE, TestState.SAFETY_TRIP}:
            session.fail(TestState.TEST_ABORTED)
    except Exception:
        logger.exception("Diagnostic WebSocket failed")
        if session is not None:
            session.fail(TestState.FAILED)
        await websocket.send_json({"type": "error", "message": "Diagnostic test failed"})
    finally:
        if session is not None:
            session.close()
        if store is not None:
            store.close()



def test_engine():
    if automated_engine is None: raise HTTPException(status_code=503,detail='Automated engine not started')
    return automated_engine

@app.post('/api/circuits/simulated-runs/{identifier}/capture')
def capture_simulated_circuit(identifier: str,index: int):
    try:return test_engine().store.capture_simulated_circuit(identifier,index)
    except KeyError as exc:raise HTTPException(status_code=404,detail='Run not found') from exc
    except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc

@app.get('/api/circuits/capabilities')
def circuit_hardware_capabilities():
    return {'hardware_control':False,'probe_connection':'NOT_DETECTABLE',
            'voltage':{'status':'UNVERIFIED','reason':'ADC scaling, protection and range require commissioning'},
            'current':{'status':'IMPLEMENTED_UNVERIFIED','reason':'INA219 #2 at 0x41 is acquired separately; bench calibration and circuit asset mapping remain unverified'},
            'resistance':{'status':'UNSUPPORTED','reason':'No verified excitation/isolation circuit'},
            'continuity':{'status':'UNSUPPORTED','reason':'No verified excitation/isolation circuit'},
            'automatic_excitation':False,'range_selection':'UNAVAILABLE',
            'supported_workflow':'Read-only operator-guided tagged engineering-value capture'}

@app.get('/api/station/status')
def station_status():
    engine=test_engine()
    return {'selected_branch':engine.circuit_power.selected_branch,
            'circuit':engine.circuit_power.snapshot(), 'motor':engine.snapshot(),
            'hardware_runtime_enabled':engine.hardware_runtime.enabled}

@app.post('/api/station/select')
def station_select(payload: BranchSelectionPayload):
    try:return test_engine().circuit_power.select(payload.branch)
    except RunRejected as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc

@app.post('/api/station/circuit/power')
def station_circuit_power(payload: CircuitPowerPayload):
    service=test_engine().circuit_power
    if not payload.on:return service.stop()
    try:return service.start(payload.duration_ms,payload.supervised_confirmed)
    except (ValueError,OSError,RuntimeError) as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc

@app.get('/api/station/circuit/{session_id}/csv')
def station_circuit_csv(session_id: str):
    import io,json
    with test_engine().store.connect() as db:
        if not db.execute('SELECT 1 FROM branch_power_sessions WHERE id=?',(session_id,)).fetchone():
            raise HTTPException(status_code=404,detail='Circuit power session not found')
        rows=db.execute('SELECT * FROM branch_power_samples WHERE session_id=? ORDER BY id',(session_id,)).fetchall()
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['session_id','received_at','source','branch','stm32_timestamp_ms','voltage_V','current_A','power_W','calibrated'])
    for row in rows:
        b=json.loads(row['record_json'])
        writer.writerow([session_id,row['received_at'],'stm32_serial','CIRCUIT',b['timestamp_ms'],
                         *[b['measurements'][key]['value'] for key in ('voltage','current','power')],b['calibrated']])
    return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="circuit-{session_id}.csv"'})

@app.get('/api/motor/hardware/status')
def hardware_motor_status():
    import json
    from diagnostic_platform.automated_engine import load_hardware_profile
    engine=test_engine();profile={};reason=''
    try:
        if engine.hardware_profile_path:
            profile=json.loads(Path(engine.hardware_profile_path).read_text())
            if not isinstance(profile,dict):profile={}
        load_hardware_profile(engine.hardware_profile_path)
        ready=True
    except (OSError,ValueError) as exc:
        reason=str(exc);ready=False
    active=engine.snapshot()
    preflight=engine.hardware_runtime.snapshot()
    return dict(profile_ready=ready,reason=reason,asset_id=profile.get('asset_id','MOTOR-001'),
                hardware_control_enabled=engine.hardware_runtime.enabled,
                hardware_control=ready and preflight['ready'],
                firmware_hardware_control=preflight.get('firmware_hardware_control'),
                preflight=preflight,
                operating_mode=profile.get('operating_mode','NORMAL'),
                power_feedback_installed=profile.get('power_feedback_installed',False),
                electrical_limits_enabled=profile.get('electrical_limits_enabled'),
                protection_limits_verified=profile.get('protection_limits_verified',False),
                supply_sensing_verified=isinstance(profile.get('supply_sensing'),dict) and profile['supply_sensing'].get('verified') is True,
                fixed_pwm_percent=profile.get('fixed_pwm_percent'),max_duration_ms=profile.get('max_duration_ms',30000),
                active_run=active if active and active['mode']=='hardware' else None)

@app.post('/api/motor/hardware/preflight')
def hardware_motor_preflight():
    try:return test_engine().preflight()
    except RunRejected as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc


@app.get('/api/automated/registry')
def automated_registry(mode: str='simulation'):
    try:return test_engine().available(mode)
    except RunRejected as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc

@app.get('/api/automated/catalog')
def automated_catalog():
    from diagnostic_platform.test_registry import experiment_catalog
    return experiment_catalog()

@app.post('/api/automated/runs',status_code=201)
def start_automated_run(payload: AutomatedRunPayload):
    try:return test_engine().start(payload.model_dump())
    except (RunRejected,RuntimeError,OSError,ValueError) as exc:
        raise HTTPException(status_code=409,detail=str(exc)) from exc

@app.get('/api/automated/runs')
def automated_runs():return test_engine().store.list()

@app.get('/api/automated/runs/{run_id}')
def automated_run(run_id: str):
    try:return test_engine().store.get(run_id)
    except KeyError as exc:raise HTTPException(status_code=404,detail='Run not found') from exc

@app.post('/api/automated/runs/{run_id}/stop')
def stop_automated_run(run_id: str,emergency: bool=False):
    active=test_engine().snapshot()
    if not active or active['id']!=run_id or active['state'] in TERMINAL:
        raise HTTPException(status_code=409,detail='Run is not active')
    return test_engine().stop(emergency)

@app.get('/api/automated/runs/{run_id}/report')
def automated_report(run_id: str):
    import json
    run=automated_run(run_id)
    if run['state'] not in TERMINAL:raise HTTPException(status_code=409,detail='Run is still active')
    return Response(json.dumps(run,indent=2,allow_nan=False),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="trace-x-{run["id"]}.json"'})

@app.get('/api/automated/runs/{run_id}/csv')
def automated_csv(run_id: str):
    from diagnostic_platform.motor_csv import render_motor_csv
    run=automated_run(run_id)
    return Response(render_motor_csv(run),media_type='text/csv',
                    headers={'Content-Disposition':f'attachment; filename="trace-x-{run["id"]}.csv"'})


@app.websocket('/ws/automated/{run_id}')
async def automated_stream(socket: WebSocket,run_id: str):
    await socket.accept()
    try:
        while True:
            active=test_engine().snapshot()
            if not active or active['id']!=run_id:
                await socket.send_json(automated_run(run_id));break
            await socket.send_json(active)
            if active.get('ended_at'):break
            await asyncio.sleep(.1)
    except WebSocketDisconnect:
        active=test_engine().snapshot()
        if active and active['id']==run_id and active['mode']=='hardware' and active['state'] not in TERMINAL:
            test_engine().stop()
    except (RuntimeError,HTTPException):
        try:await socket.close(code=1011)
        except RuntimeError:pass
    finally:
        if automated_engine:
            active=automated_engine.snapshot()
            if active and active['id']==run_id and active['mode']=='hardware' and active['state'] not in TERMINAL:
                automated_engine.stop()

if os.getenv('ADS_SERVE_DASHBOARD', '') == '1':
    mount_dashboard(app, ROOT / 'frontend' / 'dist')
