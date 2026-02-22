import numpy as np
import control as ctl
import matplotlib.pyplot as plt


s=ctl.TransferFunction.s


for K in np.arange(0, 10000, 500):
    GHs = (4000*K) / ((s**3 + 321*s*s + 40320*s + 4E04 + 4000*K))
    po = GHs.poles()
    print(f'K: {K:8.1f} [',end='')
    for p in po:
        print(f' {p:8.0f} ',end='')
    print(']')



# ctl.margin(sys) returns:
