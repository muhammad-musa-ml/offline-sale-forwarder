"""Records one sale and exits without closing the journal, as a killed register would."""
import os
import sys

sys.path.insert(0, sys.argv[1])
from saleforward.journal import Journal

journal = Journal(sys.argv[2])
journal.record("reg-0001", 1899)
os._exit(1)
