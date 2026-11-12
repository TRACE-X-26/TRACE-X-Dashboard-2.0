"""Explicit bounded circuit supply session; no automatic fault/health test."""
import copy
import threading
import time
import json
from uuid import uuid4

from .hardware_runtime import RunRejected
from .automated_storage import utcnow
from .ina219 import normalize_branches


class CircuitPowerService:
    def __init__(self, engine):
        self.engine = engine
        self.selected_branch = None
        self.current = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self.current)

    def select(self, branch):
        if branch not in ('MOTOR', 'CIRCUIT'):
            raise RunRejected('Select MOTOR or CIRCUIT')
        if not self.engine._mutex.acquire(blocking=False):
            raise RunRejected('Stop the active operation before changing branches')
        try:
            with self._lock:
                self.selected_branch = branch  # Software only: no serial or GPIO.
            return {'selected_branch': branch, 'power_changed': False}
        finally:
            self.engine._mutex.release()

    def stop(self):
        self._stop.set()
        return {'accepted': True, 'physical_stop_confirmed': False}

    def close(self):
        self.stop()
        if self._thread:
            self._thread.join(timeout=4)
            if self._thread.is_alive():
                raise RuntimeError('Circuit power owner failed to shut down')

    def start(self, duration, confirmed):
        from .automated_engine import load_hardware_profile
        self.engine.hardware_runtime.require_permission()
        profile = load_hardware_profile(self.engine.hardware_profile_path, require_motor_protection=False)
        if self.selected_branch != 'CIRCUIT':
            raise RunRejected('Select Circuit before applying circuit power')
        if profile.get('circuit_power_approved') is not True:
            raise RunRejected('Circuit relay/cutoff approval is missing from this profile')
        if confirmed is not True:
            raise RunRejected('Fresh operator supervision/cutoff confirmation required')
        if type(duration) is not int or not 100 <= duration <= 30000:
            raise RunRejected('Circuit power duration must be 100–30000 ms')
        if not self.engine._mutex.acquire(blocking=False):
            raise RunRejected('Another operation owns the hardware; retry when idle')
        try:
            if self.selected_branch != 'CIRCUIT':
                raise RunRejected('Select Circuit before applying circuit power')
            self._stop.clear()
            with self._lock:
                self.current = dict(id=str(uuid4()), branch='CIRCUIT', source='stm32_serial',
                                    state='PRECHECK', power_on=False, stop_confirmed=False,
                                    created_at=utcnow(), ended_at=None, duration_ms=duration,
                                    reason='', health_score=None)
            self._thread = threading.Thread(target=self._run, args=(profile, duration),
                                            daemon=True, name='trace-x-circuit-power')
            self._thread.start()
            return self.snapshot()
        except Exception:
            self.engine._mutex.release()
            raise

    def _update(self, **fields):
        with self._lock:
            self.current.update(fields)
            record = copy.deepcopy(self.current)
        with self.engine.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO branch_power_sessions VALUES(?,?)',
                       (record['id'], json.dumps(record, allow_nan=False)))

    def _command(self, connection, command, args=None):
        if command != 'STOP_CIRCUIT' and self._stop.is_set():
            raise RunRejected('Circuit operation cancelled')
        result = connection.execute(command, args)
        if result.get('accepted') is not True:
            raise RunRejected(command + ': ' + str(result.get('reason', 'rejected')))
        return result

    def _run(self, profile, duration):
        connection = None
        try:
            from .test_registry import REGISTRY
            connection = self.engine._connection('hardware', REGISTRY['pwm_50'], None, profile)
            connection.connect()
            caps = self.engine._read(connection, 'GET_CAPABILITIES')
            if (caps.get('device_id') != profile['device_id'] or caps.get('firmware_version') != profile['firmware_version'] or
                caps.get('operating_mode') != profile.get('operating_mode') or
                caps.get('integrity') != 'CRC32' or caps.get('circuit_power_control') is not True or
                caps.get('circuit_max_duration_ms') != 30000 or caps.get('heartbeat_timeout_ms') != 2000 or
                caps.get('circuit_relay') != 'D5/PB4/IN2' or
                not {'GET_CIRCUIT_STATUS','ARM_CIRCUIT','START_CIRCUIT','STOP_CIRCUIT'}.issubset(caps.get('commands', []))):
                raise RunRejected('Circuit power unavailable: firmware identity/permission/capability mismatch; updated firmware required')
            motor = self.engine._read(connection, 'GET_STATUS')
            if motor.get('applied_pwm_percent') != 0 or motor.get('state') not in ('STOPPED','DISARMED','LOCKOUT'):
                raise RunRejected('Motor must be stopped before circuit power')
            status = self.engine._read(connection, 'GET_CIRCUIT_STATUS')
            if status.get('power_on') is not False:
                raise RunRejected('Circuit stopped state not confirmed')
            connection.seed_sequence(max(motor.get('last_control_seq', 0), status.get('last_control_seq', 0)))
            connection.heartbeat()
            self._command(connection, 'ARM_CIRCUIT', {'supervised_confirmed': True})
            ack = self._command(connection, 'START_CIRCUIT', {'duration_ms': duration})
            if ack.get('power_on') is not True or ack.get('state') != 'RUNNING' or type(ack.get('started_ms')) is not int:
                raise RunRejected('Circuit power-on state not acknowledged')
            self._update(state='POWERED', power_on=True, started_ms=ack['started_ms'])
            deadline = time.monotonic() + duration / 1000
            while not self._stop.is_set() and time.monotonic() < deadline:
                connection.heartbeat()
                status = self.engine._read(connection, 'GET_CIRCUIT_STATUS')
                if status.get('power_on') is False:
                    if status.get('stop_reason') != 'COMPLETED':
                        raise RunRejected('Circuit stopped: ' + str(status.get('stop_reason')))
                    break
                raw = self.engine._read(connection, 'READ_MEASUREMENTS')
                branch = normalize_branches(raw)['CIRCUIT']
                if not branch['connected'] or not branch['valid']:
                    raise RunRejected('Circuit INA219 disconnected or invalid')
                if ((connection.last_timestamp_ms - branch['timestamp_ms']) & 0xffffffff) > 1500:
                    raise RunRejected('Circuit INA219 stale')
                self._update(measurements=branch)
                with self.engine.store.connect() as db:
                    db.execute('INSERT INTO branch_power_samples(session_id,received_at,record_json) VALUES(?,?,?)',
                               (self.current['id'], utcnow(), json.dumps(branch, allow_nan=False)))
                if self.engine.publish:
                    self.engine.publish(raw, 'stm32_serial')
                self._stop.wait(.3)
            self._update(state='STOPPING', reason='CANCELLED' if self._stop.is_set() else 'COMPLETED')
        except Exception as exc:
            self._update(state='FAILED', reason=str(exc))
        finally:
            confirmed = False
            if connection:
                try:
                    result = self._command(connection, 'STOP_CIRCUIT')
                    self._update(stopped_ms=result.get('stopped_ms'), shutdown_reason=result.get('stop_reason'))
                    confirmed = result.get('power_on') is False and result.get('state') in {'STOPPED', 'LOCKOUT', 'DISARMED'}
                    if not confirmed:
                        self._update(reason='Circuit power-off state not acknowledged', state='FAILED')
                except Exception as exc:
                    self._update(reason='Circuit stop unconfirmed: ' + str(exc), state='FAILED')
                try:
                    connection.disconnect()
                except Exception as exc:
                    self._update(disconnect_error=str(exc))
            try:
                current = self.snapshot()
                self._update(state='STOPPED' if confirmed and current['state'] != 'FAILED' else 'FAILED',
                             power_on=False if confirmed else None, stop_confirmed=confirmed, ended_at=utcnow())
            finally:
                self.engine._mutex.release()
