"""Procedures supported by evidence; unavailable entries are never run silently."""
from dataclasses import asdict, dataclass
from .motor_health import TEST_CATALOG

@dataclass(frozen=True)
class Procedure:
    id: str
    name: str
    pwm: int | None = None
    kind: str = 'motor'
    reason: str = ''
    requires_setup: bool = False

PROCEDURES = [Procedure('idle', 'Safe idle / stationary and zero-offset observations', 0)]
PROCEDURES += [Procedure(f'pwm_{p}', f'{p}% PWM operational response', p) for p in (10,25,50,75,100)]
PROCEDURES += [
    Procedure('pwm_ramp','Controlled PWM ramp',reason='Firmware supports one fixed duty per run; continuous ramp is not commissioned.'),
    Procedure('load_response','Weight / Load Testing',50,requires_setup=True),
    Procedure('friction_response','Excessive Friction',50,requires_setup=True),
    Procedure('steady_state','Steady-State RPM',50,requires_setup=True),
    Procedure('voltage_stability','Voltage Stability',50,requires_setup=True),
    Procedure('power_consumption','Power Consumption',50,requires_setup=True),
    Procedure('startup','Startup characteristics',reason='Acquisition timing/bandwidth and startup reference not validated.'),
    Procedure('noise','Electrical noise / sensor stability',reason='High-bandwidth acquisition and noise acceptance limits not validated.'),
    Procedure('baseline','Record healthy baseline',reason='Independent healthy labeling and repeated matched-run baseline approval required.'),
    Procedure('circuit_voltage','Circuit probe voltage',kind='circuit',reason='ADC scaling, protection, range and probe-state commissioning missing; use guided capture.'),
    Procedure('circuit_current','Circuit branch current',kind='circuit',reason='INA219 #2 identity and calibrated branch telemetry not commissioned.'),
    Procedure('continuity','Continuity / resistance',kind='circuit',reason='Verified excitation, isolation and input protection are not documented.'),
    Procedure('circuit_faults','Circuit 4 reference comparison',kind='circuit',reason='Use existing operator-guided Circuit 4 capture; rules remain provisional.'),
]
# CSV target labels exist for these exploratory duties, but no approved full protocol.
PROCEDURES += [Procedure(f'pwm_{p}',f'{p}% exploratory recording setpoint',p,
    reason='CSV target label only; duration, fixture and safety acceptance are not a validated procedure.') for p in (5,15,20)]
PROCEDURES += [Procedure(f'historical_test_{i:02d}',TEST_CATALOG.get(i,(f'Historical experiment test_{i:02d}',None))[0],
    reason='Historical run identifier is not an executable procedure; fixture/action/limits must be mapped and approved.') for i in range(1,16)]

REGISTRY = {p.id:p for p in PROCEDURES}
# These are existing simulation fault-injection scenarios, not physical fault commands.
SCENARIOS = ('healthy','overloaded','undervoltage','overheating','stalled','sensor_failure','communication_loss')

def registry(mode='simulation', fixed_pwm=None, ready=False, approved_procedures=()):
    out=[]
    for p in PROCEDURES:
        reason=p.reason
        if mode=='hardware' and not reason:
            if not ready: reason='Hardware commissioning profile and operator authorization required.'
            elif p.pwm not in (0,fixed_pwm): reason='Not the single bench-approved fixed duty.'
            elif p.requires_setup and p.id not in approved_procedures:
                reason='Individual procedure approval required in hardware profile.'
        out.append({**asdict(p),'available':not reason,'unavailable_reason':reason})
    return out


def experiment_catalog():
    """Historical experiment mappings do not expand physical permissions."""
    ids = {1:'idle',2:'pwm_10',3:'pwm_25',4:'pwm_50',5:'pwm_75',6:'pwm_100',
           8:'steady_state',9:'voltage_stability',11:'power_consumption',
           12:'load_response',13:'friction_response'}
    purposes = {
        1:'Observe stationary encoder and electrical offset',
        2:'Record response at 10% duty',3:'Record response at 25% duty',
        4:'Record response at 50% duty',5:'Record response at 75% duty',6:'Record response at 100% duty',
        7:'Find a confirmed transition from rest at increasing duty',
        8:'Measure stable encoder response in a confirmed acquisition window',
        9:'Assess branch voltage variability at constant duty',
        10:'Capture current relative to a device-timestamped start',
        11:'Assess synchronized voltage times current',
        12:'Compare runs under documented externally applied loads',
        13:'Compare runs under documented externally applied resistance',
    }
    catalog = []
    for number,(name,pwm) in TEST_CATALOG.items():
        executable = ids.get(number)
        catalog.append(dict(test_number=number,name=name,purpose=purposes[number],
            execution_id=executable or f'historical_test_{number:02d}',requested_pwm=pwm,
            execution_pwm=REGISTRY[executable].pwm if executable else None,
            equipment=['STM32-F401RE','MD10C','Motor INA219 #1','Encoder','Physical cutoff'],
            sensors=['branch_voltage','branch_current','encoder'],
            commands=['GET_STATUS','GET_CAPABILITIES','READ_MEASUREMENTS'] +
                     (['ARM_TEST','SET_PWM','START_TEST','STOP_TEST'] if executable and REGISTRY[executable].pwm else []),
            duration='Operator-selected bounded duration, maximum 30 seconds',
            completion='Confirmed STM32 start/stop events and zero applied output acknowledgment',
            baseline_features=['voltage','current','power','rpm'],
            safety='Fresh operator authorization; commissioned PWM/current/supply limits; heartbeat and local deadline',
            operator_setup='Record load ID, attached mass in grams, fixture and condition; operator applies mechanical setup' if number in (12,13) else 'Record motor, load, direction, calibration and procedure context',
            implementation='IMPLEMENTED' if executable else 'UNAVAILABLE',
            verification='Physical procedure not verified by this agent',
            limitation=('Only the approved 50% duty can be eligible after live prechecks' if executable else
                        'Dedicated procedure commissioning required; historical measurements remain available')))
    return catalog
