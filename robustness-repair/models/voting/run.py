import sys
from os import path

sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from repair import *

alphabet = ["back", "confirm", "password", "select", "vote",
            "eo.enter", "eo.exit", "v.enter", "v.exit"]


r = Repair(
    sys=["sys.lts"],
    env_p=["env.lts"],
    safety=["p2.lts"],
    preferred={   # rank the preferred behavior by importance
        PRIORITY3: ["back.lts"],
        PRIORITY2: [
            # "patch1.lts",
            # "patch2.lts"
        ],
        PRIORITY1: [],  
        PRIORITY0: []
    },
    progress=["confirm"],
    alphabet=alphabet,  # \alpha M \union \alpha E
    controllable={  # rank the controllable events by cost
        PRIORITY3: ["eo.enter", "eo.exit", "v.enter", "v.exit"],
        PRIORITY2: [],
        PRIORITY1: [], 
        PRIORITY0: ["back", "confirm", "password", "select", "vote"]
    },
    observable={    # rank observable events by cost
        PRIORITY3: [],
        PRIORITY2: ["eo.exit", "v.exit", "eo.enter", "v.enter"],
        PRIORITY1: [], 
        PRIORITY0: ["back", "confirm", "password", "select", "vote"]
    }
)

result = r.synthesize(6)
for c in result:
    print(r.fsm2fsp(c["M_prime"], c["observable"], name="M"))
