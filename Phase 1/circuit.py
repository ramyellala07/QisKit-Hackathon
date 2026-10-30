from qiskit.circuit.library import DraperQFTAdder
c = DraperQFTAdder(2, kind="fixed")
print(c.decompose().draw())