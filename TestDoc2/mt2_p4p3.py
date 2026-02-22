import numpy as np
import matplotlib.pyplot as plt
from control import tf, bode_plot
import control as ctl
import matplotlib

# Set plot style
matplotlib.rcParams.update({'font.size': 12})
plt.figure(figsize=(10, 8))

s = ctl.TransferFunction.s

# Create the transfer function
# sys = tf(num, den)
sys = (2.0E04) / ((s+0.1)*(s+31.6)**2)

# Generate the Bode plot
pdata = bode_plot(sys, dB=True, Hz=False, deg=True, omega_limits=(0.01, 1000))
#
# # Customize the plots
# plt.subplot(211)  # Select the magnitude plot
# plt.grid(True, which="both")
# plt.ylabel('Magnitude (dB)')
# plt.title(r'Bode Plot of $G_{4.3}(s) = \frac{200(s+2)}{(s+0.1)(s+31.6)^2}$')
#
# plt.subplot(212)  # Select the phase plot
#
# plt.grid(True, which="both")
# plt.ylabel('Phase (degrees)')
# plt.xlabel('Frequency (rad/s)')

plt.tight_layout()

# Print the transfer function for reference
print(f"Transfer Function: {sys}")

# Optional: Calculate key points of interest
# Gain at DC (ω=0)
dc_gain = 400/99.856  # Evaluate at s=0
print(f"DC Gain: {dc_gain:.2f} ({20*np.log10(dc_gain):.2f} dB)")

gm, pm, wg, wp = ctl.margin(sys)
print('Margins: ')
print('    Gain Margin: ', 20*np.log10(gm), '(db)  omega = ', wg)
print('    Phase Margin: ', pm, '(deg) omega = ', wp)
print('    ')


plt.show()
