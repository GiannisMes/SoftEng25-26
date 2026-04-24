import subprocess
import sys
import os
import time

# --- Configuration ---
# Get the directory where this script (test_cli.py) is located
current_dir = os.path.dirname(os.path.abspath(__file__))

# Point to cli.py in the sibling 'cli' directory: ../cli/cli.py
CLI_SCRIPT = os.path.join(current_dir, "..", "cli", "cli.py")

PYTHON_EXE = sys.executable

# Test Data Constants 
S1 = "2026-02-12 17:00:00"
E1 = "2026-02-12 17:45:00"
S2 = "2026-02-12 18:00:00"
E2 = "2026-02-12 18:45:00"

# This point id matches to the charger at Sounio
POINT_ID = "650055"

def run_step(command_args, description):
    """Runs a single CLI command and waits for user input."""
    
    # Verify cli.py exists before running
    if not os.path.exists(CLI_SCRIPT):
        print(f"ERROR: Could not find cli.py at: {CLI_SCRIPT}")
        sys.exit(1)

    print("=" * 60)
    print(f"ACTION: {description}")
    print(f"COMMAND: se2517 {' '.join(command_args)}")
    print("-" * 60)
    
    try:
        # Call the cli.py script using the absolute path
        subprocess.run([PYTHON_EXE, CLI_SCRIPT] + command_args, check=False)
    except Exception as e:
        print(f"Error executing command: {e}")

    print("=" * 60)
    # Pause for user input to proceed to the next step
    input("Press [Enter] to continue...")
    print("\n")

def main():

    # Define the Sequence of Commands (Table from image)
    steps = [
        # 1. Healthcheck
        (["healthcheck"], "Έλεγχος λειτουργίας (Healthcheck)"),
        
        # 2. Reset Points
        (["resetpoints"], "Αρχικοποίηση (Reset Points)"),
        
        # 3. Add Points
        (["addpoints", "--source", "database/new_points.csv"], "Προσθήκη κάποιων σημείων (Add Points)"),
        
        # 4. Healthcheck (Again)
        (["healthcheck"], "Έλεγχος (Healthcheck)"),
        
        # 5. Points Available
        (["points", "--status", "available"], "Επισκόπηση (Status: Available)"),
        
        # 6. Points Charging
        (["points", "--status", "charging"], "Επισκόπηση (Status: Charging)"),
        
        # 7. Points Offline
        (["points", "--status", "offline"], "Επισκόπηση (Status: Offline)"),
        
        # 8. Point Info X
        (["point", "--id", POINT_ID], f"Πληροφορίες σημείου {POINT_ID}"),
        
        # 9. Reserve X
        (["reserve", "--id", POINT_ID], f"Δέσμευση σημείου {POINT_ID}"),
        
        # 10. Points Reserved
        (["points", "--status", "reserved"], "Επισκόπηση (Status: Reserved)"),
        
        # 11. Point Info X
        (["point", "--id", POINT_ID], f"Πληροφορίες σημείου {POINT_ID}"),
        
        # 12. Update Point (Release/Available)
        (["updpoint", "--id", POINT_ID, "--status", "available"], "Αποδέσμευση (Update to Available)"),
        
        # 13. Point Info X
        (["point", "--id", POINT_ID], f"Πληροφορίες σημείου {POINT_ID}"),
        
        # 14. Reserve X (Again)
        (["reserve", "--id", POINT_ID], f"Δέσμευση σημείου {POINT_ID}"),
        
        # 15. Points Reserved Check
        (["points", "--status", "reserved"], "Έλεγχος δεσμευμένων σημείων"),
        
        # 16. New Session 1
        ([
            "newsession", "--id", POINT_ID, 
            "--starttime", S1, "--endtime", E1, 
            "--startsoc", "10", "--endsoc", "30", 
            "--totalkwh", "15", "--kwhprice", "0.5", 
            "--amount", "7.5"
        ], "Καταγραφή φόρτισης 1 (E1 > S1)"),
        
        # 17. Point Status History (S1 -> E1)
        (["pointstatus", "--id", POINT_ID, "--from", S1, "--to", E1], f"Ιστορικό σημείου {POINT_ID} ({S1} - {E1})"),
        
        # 18. Point Info X
        (["point", "--id", POINT_ID], f"Πληροφορίες σημείου {POINT_ID}"),
        
        # 19. New Session 2
        ([
            "newsession", "--id", POINT_ID, 
            "--starttime", S2, "--endtime", E2, 
            "--startsoc", "50", "--endsoc", "80", 
            "--totalkwh", "20", "--kwhprice", "0.6", 
            "--amount", "12"
        ], "Καταγραφή φόρτισης 2 (S2 > E1)"),
        
        # 20. Session History (S1 -> E2)
        (["sessions", "--id", POINT_ID, "--from", S1, "--to", E2], f"Ιστορικό συνεδριών σημείου {POINT_ID}"),
        
        # 21. Point Status History (S1 -> E2)
        (["pointstatus", "--id", POINT_ID, "--from", S1, "--to", E2], f"Κατάσταση σημείου {POINT_ID} (Full History)")
    ]

    # 3. Execute Loop
    try:
        for cmd, desc in steps:
            run_step(cmd, desc)
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    finally:
        print("Test script completed.")

if __name__ == "__main__":

    main()
