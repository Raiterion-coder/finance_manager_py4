import sqlite3
import sys
from pathlib import Path

# Если приложение "заморожено" (например, скомпилировано в .exe с помощью PyInstaller),
# то база данных будет находиться рядом с исполняемым файлом.
# Иначе — рядом с исходным кодом .py.
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "finance.db"

# Класс для работы с локальной базой данных финансов
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cur = self.conn.cursor()

        # Таблица счетов
        cur.execute('''
            CREATE TABLE IF NOT EXISTS accounts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                balance REAL
            )
        ''')

        # Таблица транзакций
        cur.execute('''
            CREATE TABLE IF NOT EXISTS transactions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                account_id INTEGER,
                category TEXT,
                amount REAL,
                comment TEXT,
                photo BLOB
            )
        ''')
        self.conn.commit()

    # Добавление нового счёта
    def add_account(self, name, balance=0):
        cur = self.conn.cursor()
        cur.execute('INSERT INTO accounts(name,balance) VALUES(?,?)', (name, balance))
        self.conn.commit()

    # Возвращает список всех счетов
    def list_accounts(self):
        return self.conn.execute('SELECT * FROM accounts').fetchall()

    # Обновляет баланс счёта
    def update_account_balance(self, account_id, delta):
        cur = self.conn.cursor()
        cur.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (delta, account_id))
        self.conn.commit()

    # Добавляет новую транзакцию в базу данных
    def add_transaction(self, date, account_id, category, amount, comment, photo_file=None):
        photo_data = None
        if photo_file:
            with open(photo_file, "rb") as f:
                photo_data = f.read()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO transactions(date, account_id, category, amount, comment, photo) VALUES (?, ?, ?, ?, ?, ?)",
            (date, account_id, category, amount, comment, photo_data)
        )
        self.conn.commit()

    # Возвращает список всех транзакций с указанием счёта и категории
    def list_transactions(self):
        q = """
        SELECT t.id, t.date, a.name as account, t.category, t.amount, t.comment, t.photo
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        """
        return self.conn.execute(q).fetchall()

    # Удаляет транзакцию по дате, имени счёта, категории и сумме
    # После удаления корректирует баланс счёта
    def delete_transaction(self, date, account_name, category, amount):
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE name=?", (account_name,))
        acc = cur.fetchone()
        if not acc:
            raise ValueError("Счёт не найден")
        account_id = acc["id"]

        cur.execute("""
            DELETE FROM transactions
            WHERE date=? AND account_id=? AND category=? AND amount=?
        """, (date, account_id, category, amount))
        self.conn.commit()
        self.update_account_balance(account_id, -amount)

    # Извлекает фото из транзакции (если оно есть)
    def get_transaction_photo(self, date, account_name, category, amount):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT t.photo FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.date=? AND a.name=? AND t.category=? AND t.amount=?
        """, (date, account_name, category, amount))
        row = cur.fetchone()
        if row and row["photo"]:
            import tempfile
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_file.write(row["photo"])
            tmp_file.close()
            return tmp_file.name
        return None
