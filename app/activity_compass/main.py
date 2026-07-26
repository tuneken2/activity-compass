from __future__ import annotations

import argparse

from .api import start_api
from .automation import MaintenanceWorker
from .db import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Activity Compass")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db")
    parser.add_argument("--no-ui", action="store_true")
    args = parser.parse_args()

    db = Database(args.db)
    server, api_thread = start_api(db, args.port)
    maintenance = MaintenanceWorker(db)
    maintenance.start()
    if args.no_ui:
        print(f"Activity Compass API: http://127.0.0.1:{args.port}")
        try:
            api_thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            maintenance.stop()
        return

    from .ui import ActivityCompassApp

    app = ActivityCompassApp(db)
    try:
        app.mainloop()
    finally:
        server.shutdown()
        maintenance.stop()


if __name__ == "__main__":
    main()
