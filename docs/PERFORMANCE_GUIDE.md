# Performance & runtime review (Fedora GNOME)

Automated AST checks do not measure GUI speed. Compare a *baseline* to the application after any optimization. Keep terminal logs out of public releases.

## Observe idle performance

1. Start only one Control Center instance: `/usr/bin/python3 main.py`.
2. Open Overview and wait 30 seconds; note whether CPU utilization settles and timers update.
3. Open Performance and wait 30 seconds; check that updates occur approximately every 8 seconds, without UI stalls.
4. Switch pages repeatedly; verify no increasing lag or runaway memory use.
5. In a separate terminal, run `ps -C python3 -o pid,rss,%cpu,etime,args` to inspect candidate processes, and confirm the correct PID before attributing values.
6. Close the Control Center; verify the process exits normally.

## Collect maximum memory use (optional)

```bash
cd ~/Projects/midnight-core-control-center
/usr/bin/time -v /usr/bin/python3 main.py 2> /tmp/midnight-control-timing.log
# Close app normally to finish the measurements
sed -n '/Elapsed (wall clock) time/,/Maximum resident set size/p' /tmp/midnight-control-timing.log
```

*The elapsed time above is the entire time until the GUI closes, **not** startup time.* For startup responsiveness, compare window appearance manually or use a purpose-built on-screen timing trace; do not label process lifetime as startup latency.

## Investigate exceptions and warnings

- Check terminal output for tracebacks. Errors from `Gtk.MessageDialog.format_secondary_text` require GTK4-compatible implementation.
- Occasional GDK frame timing warnings may be environment/driver related; assess actual impact rather than assuming they explain every crash.
- Review pages for blocking subprocess calls on the GTK main thread; diagnostics should perform slow I/O off-thread and dispatch UI updates to the main loop.
- Ensure periodic refreshes cease when their page/window is destroyed to avoid duplicate timers after reopening.
- The app should never `sudo` itself; privileged Plymouth changes must request separate authorization.

## Release acceptance

- [ ] No Python traceback when opening any page
- [ ] No visible freeze during system/service diagnostics
- [ ] No excessive CPU at idle
- [ ] No steadily increasing process memory during ordinary page navigation
- [ ] Close and reopen works without duplicate windows or stale callbacks
- [ ] Test report notes any unresolved limitations
