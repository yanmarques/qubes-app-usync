path = u.sync
bin_template = usync.template
bin_path = ~/.local/bin/usync
stable_branch =  dev
upstream = https://github.com/computacaoUnisul/u.sync.git

install: download
	@cd $(path); \
		pip3 install -r requirements.txt --user; \
		cat ../$(bin_template) | sed -e "s|INSTALLATION_DIR|`pwd`|" \
		> $(bin_path)

	@chmod 755 $(bin_path)

download:
	@git clone $(upstream) -b $(stable_branch) $(path); \
		case "$$?" in 127) exit 1 ;; esac

test: install
	@virtualenv venv
	@source venv/bin/activate; \
		cd $(path); \
		pip install -r requirements_dev.txt; \
		cd src/; \
		pytest tests/

reinstall:
	@make clean
	@make install

clean:
	@rm -rf u.sync
	@rm -f $(bin_path)
