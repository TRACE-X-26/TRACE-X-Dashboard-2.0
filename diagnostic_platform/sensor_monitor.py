"""Opt-in ADS JSON acquisition: READ_MEASUREMENTS only, no heartbeat or actuation."""
import threading
from .collector import ExperimentRecorder

class SensorMonitor:
    def __init__(self,engine,port,publish,directory):
        self.engine,self.port,self.publish,self.directory=engine,port,publish,directory
        self._stop=threading.Event();self._thread=None
    def start(self):
        self._thread=threading.Thread(target=self._run,daemon=True,name='ina219-read-only')
        self._thread.start()
    def close(self):
        self._stop.set()
        if self._thread:self._thread.join(timeout=2)
    def _run(self):
        recorder=None
        try:
            recorder=ExperimentRecorder(self.directory,'dual-ina219-monitor')
            while not self._stop.is_set():
                try:
                    result=self.engine.read_sensors(self.port)
                    if result is not None:
                        self.publish(result);recorder.record(result)
                except Exception:
                    self.publish(None) # Last values become stale, never synthetic zero.
                self._stop.wait(1)
        finally:
            if recorder:recorder.close()
