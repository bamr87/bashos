.PHONY: backup install dry-run uninstall check brew update tui

backup:
	./backup.sh

install:
	./install.sh

dry-run:
	./install.sh --dry-run

uninstall:
	./uninstall.sh

check:
	./check.sh

brew:
	brew bundle install --file=Brewfile

update:
	./tui.sh update

tui:
	./tui.sh
