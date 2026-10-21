"""Desktop entry point; also used by the Windows executable."""
import multiprocessing


if __name__ == "__main__":
    multiprocessing.freeze_support()
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from desktop.smoke import run_smoke
        sys.exit(run_smoke(sys.argv[2]))
    else:
        from desktop.app import main
        main()
