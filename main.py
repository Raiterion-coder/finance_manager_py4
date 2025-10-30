import os
import sys
from datetime import datetime
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, uic
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
from app.database import Database
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Если программа запущена как exe
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent  # папка, где лежит .exe
else:
    BASE_DIR = Path(__file__).resolve().parent  # папка, где лежит main.py


# Корректный путь к ресурсам (для exe и разработки)
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):  # при запуске через PyInstaller
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def resource(rel):
    return str(QtCore.QDir.current().filePath(rel))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(resource_path("ui/main_window.ui"), self)
        self.db = Database()

        # Настройка таблиц
        self.tblAccounts.setColumnCount(2)
        self.tblAccounts.setHorizontalHeaderLabels(["Название", "Баланс"])
        self.tblAccounts.horizontalHeader().setStretchLastSection(True)  # растягивание последнего столбца
        self.tblAccounts.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tblAccounts.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.btnShowChart.clicked.connect(self.show_chart)  # кнопка «Показать график» вызывает метод show_chart

        # Настройка таблицы транзакций
        self.tblTransactions.setColumnCount(6)
        self.tblTransactions.setHorizontalHeaderLabels(["Дата", "Счёт", "Категория", "Сумма", "Комментарий", "Фото"])
        self.tblTransactions.horizontalHeader().setStretchLastSection(True)
        self.tblTransactions.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tblTransactions.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        # Кнопки
        self.refresh_tables()  # заполнение таблицы данными из базы
        self.btnAddAccount.clicked.connect(self.add_account)
        self.btnAddTx.clicked.connect(self.on_add_transaction)
        self.btnShowImage.clicked.connect(self.show_image)
        self.btnDelAccount.clicked.connect(self.delete_account)
        self.btnDelTx.clicked.connect(self.delete_transaction)

    # Обновление таблицы счетов и транзакций
    def refresh_tables(self):
        # --- Счета ---
        accs = self.db.list_accounts()
        self.tblAccounts.setRowCount(0)
        for i, a in enumerate(accs):
            self.tblAccounts.insertRow(i)
            self.tblAccounts.setItem(i, 0, QtWidgets.QTableWidgetItem(a['name']))
            self.tblAccounts.setItem(i, 1, QtWidgets.QTableWidgetItem(str(a['balance'])))

        # --- Транзакции ---
        txs = self.db.list_transactions()
        self.tblTransactions.setRowCount(0)
        for i, t in enumerate(txs):
            self.tblTransactions.insertRow(i)
            self.tblTransactions.setItem(i, 0, QtWidgets.QTableWidgetItem(t['date']))
            self.tblTransactions.setItem(i, 1, QtWidgets.QTableWidgetItem(t['account']))
            self.tblTransactions.setItem(i, 2, QtWidgets.QTableWidgetItem(t['category']))
            self.tblTransactions.setItem(i, 3, QtWidgets.QTableWidgetItem(str(t['amount'])))
            self.tblTransactions.setItem(i, 4, QtWidgets.QTableWidgetItem(t['comment']))
            has_photo = t['photo'] is not None
            self.tblTransactions.setItem(i, 5, QtWidgets.QTableWidgetItem("📷" if has_photo else "-"))

    # Добавление счета
    def add_account(self):
        name, ok = QtWidgets.QInputDialog.getText(self, 'Добавить счёт', 'Название счёта:')
        if not ok or not name.strip():
            return

        # Окно ввода баланса
        balance, ok = QtWidgets.QInputDialog.getDouble(
            self, 'Начальный баланс', 'Введите начальный баланс:', 0.0,
            -999999999, 999999999, 2
        )
        if not ok:
            return
        # Добавление счёта в базу данных и обновление таблицы
        self.db.add_account(name.strip(), balance)
        self.refresh_tables()

    # Постройка графика для счета
    def show_chart(self):
        accounts = self.db.list_accounts()
        if not accounts:
            QtWidgets.QMessageBox.warning(self, "Нет счетов", "Сначала создайте хотя бы один счёт.")
            return

        items = [f"{a['id']} - {a['name']}" for a in accounts]
        item, ok = QtWidgets.QInputDialog.getItem(self, "Выбор счёта", "Выберите счёт:", items, 0, False)
        if not ok or not item:
            return

        selected_id = int(item.split(" - ")[0])
        account = next((a for a in accounts if a["id"] == selected_id), None)
        if not account:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Счёт не найден.")
            return

        txs = [
            t for t in self.db.list_transactions()
            if self.db.conn.execute(
                "SELECT id FROM accounts WHERE name=?", (t["account"],)
            ).fetchone()["id"] == selected_id
        ]

        if not txs:
            QtWidgets.QMessageBox.information(self, "Нет данных", "Для выбранного счёта нет транзакций.")
            return

        daily = {}
        for t in txs:
            d = t["date"]
            amt = float(t["amount"])
            daily[d] = daily.get(d, 0) + amt

        # Сортировка дат и вычисление накопительного баланса
        try:
            dates = [datetime.strptime(d, "%Y-%m-%d") for d in sorted(daily.keys())]
        except Exception:
            dates = sorted(daily.keys())

        balance = []
        current_balance = account["balance"]  # Текущий баланс в базе

        total_transactions = sum(daily.values())
        start_balance = current_balance - total_transactions

        running_balance = start_balance
        for d in sorted(daily.keys()):
            running_balance += daily[d]
            balance.append(running_balance)

        # Строим график
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"График счёта: {account['name']}")
        dialog.resize(900, 600)

        fig = Figure(figsize=(9, 6))
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(canvas)

        ax.plot(dates, balance, marker='o', linestyle='-', linewidth=2)
        ax.grid(True)
        ax.set_title(f"Изменение баланса: {account['name']}")
        ax.set_xlabel("Дата")
        ax.set_ylabel("Баланс, ₽")

        ax.text(dates[-1], balance[-1], f"{balance[-1]:,.2f} ₽", fontsize=10, color='blue', ha='left', va='bottom')

        canvas.draw()
        dialog.exec_()

    # Удаление счета
    def delete_account(self):
        row = self.tblAccounts.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите счёт для удаления")
            return

        name = self.tblAccounts.item(row, 0).text()

        reply = QtWidgets.QMessageBox.question(
            self, "Подтверждение",
            f"Удалить счёт '{name}' и все связанные транзакции?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        cur = self.db.conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE name=?", (name,))
        acc = cur.fetchone()
        if not acc:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Счёт не найден.")
            return

        account_id = acc["id"]

        txs = self.db.conn.execute(
            "SELECT date, category, amount FROM transactions WHERE account_id=?",
            (account_id,)
        ).fetchall()

        # Удаление каждой транзакции через метод delete_transaction()
        for t in txs:
            try:
                self.db.delete_transaction(t["date"], name, t["category"], t["amount"])
            except Exception as e:
                print(f"[WARNING] Ошибка при удалении транзакции: {e}")

        self.db.conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        self.db.conn.commit()

        self.refresh_tables()
        QtWidgets.QMessageBox.information(self, "Готово", f"Счёт '{name}' и все связанные транзакции удалены.")

    # Добавление транзакции
    def on_add_transaction(self):
        dlg = QtWidgets.QDialog(self)
        uic.loadUi(resource_path("ui/add_transaction.ui"), dlg)

        dateEdit = dlg.findChild(QtWidgets.QDateEdit, "dateEdit")
        cmbAccount = dlg.findChild(QtWidgets.QComboBox, "cmbAccount")
        edtCategory = dlg.findChild(QtWidgets.QLineEdit, "edtCategory")
        spinAmount = dlg.findChild(QtWidgets.QDoubleSpinBox, "spinAmount")
        edtComment = dlg.findChild(QtWidgets.QLineEdit, "edtComment")
        buttonBox = dlg.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
        btnAddPhoto = dlg.findChild(QtWidgets.QPushButton, "btnAddPhoto")
        btnOpenPhoto = dlg.findChild(QtWidgets.QPushButton, "btnOpenPhoto")
        lblPhotoPath = dlg.findChild(QtWidgets.QLabel, "lblPhotoPath")

        photo_path = None

        # Загружаем счета
        accounts = self.db.list_accounts()
        for a in accounts:
            cmbAccount.addItem(a["name"], a["id"])

        # Выбор фото
        def select_photo():
            nonlocal photo_path
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Выберите фото", "", "Изображения (*.png *.jpg *.jpeg *.bmp)"
            )
            if file_path:
                photo_path = file_path  # сохраняем путь для записи в BLOB
                lblPhotoPath.setText(Path(file_path).name)

        def open_photo():
            if photo_path and Path(photo_path).exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(photo_path))
            else:
                QtWidgets.QMessageBox.warning(self, "Фото", "Фото не выбрано или не найдено.")

        btnAddPhoto.clicked.connect(select_photo)
        btnOpenPhoto.clicked.connect(open_photo)

        # Сохранение транзакции
        def handle_accept():
            date = dateEdit.date().toString("yyyy-MM-dd")
            account_id = cmbAccount.currentData()
            category = edtCategory.text().strip()
            amount = float(spinAmount.value())
            comment = edtComment.text().strip()

            if account_id is None:
                QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите счёт")
                return
            if amount == 0:
                QtWidgets.QMessageBox.warning(self, "Ошибка", "Сумма не может быть 0")
                return

            rbtnExpense = dlg.findChild(QtWidgets.QRadioButton, "rbtnExpense")

            if rbtnExpense.isChecked():
                amount = -abs(amount)  # расход -> отрицательное число
            else:
                amount = abs(amount)  # доход -> положительное число

            self.db.add_transaction(date, account_id, category, amount, comment, photo_path)
            self.db.update_account_balance(account_id, amount)
            dlg.accept()

        buttonBox.accepted.connect(handle_accept)
        buttonBox.rejected.connect(dlg.reject)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.refresh_tables()

    # Удаление транзакции
    def delete_transaction(self):
        row = self.tblTransactions.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите транзакцию для удаления")
            return

        date = self.tblTransactions.item(row, 0).text()
        account = self.tblTransactions.item(row, 1).text()
        category = self.tblTransactions.item(row, 2).text()
        amount = float(self.tblTransactions.item(row, 3).text())

        reply = QtWidgets.QMessageBox.question(
            self, "Подтверждение",
            f"Удалить транзакцию '{category}' ({amount})?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.db.delete_transaction(date, account, category, amount)
            self.refresh_tables()
            QtWidgets.QMessageBox.information(self, "Готово", "Транзакция и фото удалены (если было).")

        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Ошибка", str(e))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить транзакцию:\n{e}")

    # Просмотр изображения
    def show_image(self):
        row = self.tblTransactions.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите транзакцию")
            return

        date = self.tblTransactions.item(row, 0).text()
        account = self.tblTransactions.item(row, 1).text()
        category = self.tblTransactions.item(row, 2).text()
        amount = float(self.tblTransactions.item(row, 3).text())

        photo_file = self.db.get_transaction_photo(date, account, category, amount)
        if photo_file:
            QDesktopServices.openUrl(QUrl.fromLocalFile(photo_file))
        else:
            QtWidgets.QMessageBox.information(self, "Фото", "Фото не найдено для этой транзакции.")

    # Обработка нажатий клавиш клавиатуры
    def keyPressEvent(self, event):
        # Клавиша Delete
        if event.key() == QtCore.Qt.Key_Delete:
            # Если активна таблица транзакций и есть выделенная строка
            if self.tblTransactions.hasFocus():
                self.delete_transaction()
            # Если активна таблица счетов
            elif self.tblAccounts.hasFocus():
                self.delete_account()
            else:
                QtWidgets.QMessageBox.information(
                    self, "Удаление", "Выберите таблицу (счета или транзакции) для удаления элемента."
                )


# Запуск

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
