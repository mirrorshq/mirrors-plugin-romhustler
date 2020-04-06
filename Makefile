plugin=romhustler
prefix=/usr

all:

clean:
	fixme

install:
	install -d -m 0755 "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins"
	cp -r $(plugin) "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins"
	find "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins/$(plugin)" -type f | xargs chmod 644
	find "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins/$(plugin)" -type d | xargs chmod 755
	find "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins/$(plugin)" -name "*.py" | xargs chmod 755

uninstall:
	rm -rf "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins/$(plugin)"

.PHONY: all clean install uninstall
