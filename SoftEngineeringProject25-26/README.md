# Οδηγίες για να κατεβεί το project

Στο db_config αρχείο θα θέσετε τα στοιχεία που αντοιστοιχούν στη βάση σας, εκτός από το όνομα, το οποίο πρέπει να είναι softeng25_17.

Απαιτείται να υπάρχει κατεβασμένη στη συσκευή η python.<br>
Έπειτα πηγαίνετε στο φάκελο όπου έχει τοποθετηθεί το project και εκτελείτε pip install 'module', όπου module είναι το όνομα του python module.<br>
Αυτή η εντολή πρέπει να γίνει για τα εξής modules: flask, flask_cors, marshmallow, mysql-connector-python, stripe

Μετά εκτελείτε την εντολή python -m backend.populate για να δημιουργηθεί η βάση δεδομένων.<br>
Με python run.py δημιουργείται ένας flask server, και ψάχνοντας το 'http://127.0.0.1:9876/' σε έναν web browser, θα εμφανιστεί η ιστοσελίδα.
