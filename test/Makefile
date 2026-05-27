# defaults
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# Enable cocotb/Icarus waveform dumping.
# With Icarus, cocotb writes an FST waveform under sim_build/, normally:
#   sim_build/$(TOPLEVEL).fst
WAVES ?= 1

# Verilog sources
VERILOG_SOURCES += ../hardware/verilog/*.v

# TOPLEVEL is the name of the toplevel module in your Verilog file
TOPLEVEL = Wrapper

# MODULE is the basename of the Python test file
MODULE = testGCN

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim

.PHONY: wave
wave:
	gtkwave sim_build/$(TOPLEVEL).fst

.PHONY: list-waves
list-waves:
	find . \( -name "*.fst" -o -name "*.vcd" \) -print
