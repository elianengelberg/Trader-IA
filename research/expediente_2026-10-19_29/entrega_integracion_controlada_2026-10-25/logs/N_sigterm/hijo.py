import signal, sys, time, pathlib
out = pathlib.Path(sys.argv[1])
signal.signal(signal.SIGTERM, lambda *a: (out.write_text("python recibió SIGTERM\n"), sys.exit(0)))
out.write_text("python vivo, sin SIGTERM\n")
time.sleep(6)
