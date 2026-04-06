from app.services.printer_manager import PRINTERS

print("Current printer status:")
for pid, p in PRINTERS.items():
    print(f"Printer {pid}: queue_size={p['queue'].qsize()}, connected={p['connection'].connected}")