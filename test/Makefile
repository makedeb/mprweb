T = $(sort $(wildcard *.t))

PROVE := $(shell command -v prove 2> /dev/null)

MAKEFLAGS = -j1

# IMPORTANT: `sh` should come somewhere AFTER `pytest`.
check: sh

ifdef PROVE
sh:
	prove .
else
sh: $(T)
endif

$(T):
	@echo "*** $@ ***"; $(SHELL) $@ -v

.PHONY: check coverage $(FOREIGN_TARGETS) clean $(T)
