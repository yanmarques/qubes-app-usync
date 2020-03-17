path = u.sync
bin_template = usync.template
bin_path = ~/.local/bin
stable_branch =  dev
upstream = https://github.com/computacaoUnisul/u.sync.git

.PHONY = build download help rebuild clean

.DEFAULT = help

help:
	@echo "make build"
	@echo "	download and install u.sync dependency"
	@echo "make download"
	@echo "	get dependency from upstream and save locally"
	@echo "make check"
	@echo "	check against usync installation"
	@echo "make rebuild"
	@echo "	removes build files and build"
	@echo "make clean"
	@echo "	remove build files"

build: download
	@pushd $(path); \
		pip3 install -r requirements.txt --user; \
		popd; \
		cat $(bin_template) | \
		sed -e "s|INSTALLATION_DIR|`pwd`|" \
		> $(bin_path)/usync

	@chmod 755 $(bin_path)/usync

download:
	@git clone $(upstream) -b $(stable_branch) $(path); \
		case "$$?" in 127) exit 1 ;; esac

check:
	@usync -h &> /dev/null; \
		case "$$?" in \
			0) echo 'Test Succeeded!!!!' ;; \
			*) (echo 'Test Failed.^^^^' ; exit 1) \
		;; esac

rebuild:
	make clean
	make build

clean:
	rm -rf $(path)
	rm -f $(bin_path)/usync
