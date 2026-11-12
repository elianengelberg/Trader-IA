"""Corre pytest con el reloj de pared fijado (time-machine): python con_reloj.py <ISO> <args de pytest...>"""
import sys
from datetime import datetime

import pytest
import time_machine

with time_machine.travel(datetime.fromisoformat(sys.argv[1]), tick=True):
    sys.exit(pytest.main(sys.argv[2:]))
