import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import aiohttp
import json
import io
import os
from PIL import Image, ImageTk

# --- Настройки ---
FAVORITES_FILE = "favorites.json"

# --- Логика работы с API ---
class GitHubAPIError(Exception):
    pass

async def fetch_user_data(session: aiohttp.ClientSession, username: str):
    url = f"https://api.github.com/users/{username}"
    async with session.get(url) as response:
        if response.status == 200:
            data = await response.json()
            # Загрузка аватара
            avatar_url = data.get("avatar_url")
            async with session.get(avatar_url) as img_resp:
                if img_resp.status == 200:
                    img_bytes = await img_resp.read()
                    data["avatar_image"] = Image.open(io.BytesIO(img_bytes))
                else:
                    data["avatar_image"] = None
            return data
        elif response.status == 404:
            raise GitHubAPIError("Пользователь не найден.")
        else:
            raise GitHubAPIError(f"Ошибка {response.status} от сервера.")

# --- Логика работы с избранным (JSON) ---
def load_favorites():
    if not os.path.exists(FAVORITES_FILE):
        return {"favorites": []}
    with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if "favorites" in data else {"favorites": []}
        except json.JSONDecodeError:
            return {"favorites": []}

def save_favorites(data):
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- Основное окно приложения ---
class GitHubUserFinderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GitHub User Finder")
        self.geometry("900x650")
        
        self.current_user_data = None
        self.avatar_cache = {} # Кэш для изображений, чтобы они не исчезали

        self.create_widgets()
        self.load_favorites_to_tree()

    def create_widgets(self):
        # Верхняя панель: Поиск
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_frame, text="Логин пользователя:").pack(side="left")
        
        self.username_var = tk.StringVar()
        self.entry = ttk.Entry(top_frame, textvariable=self.username_var, width=35)
        self.entry.pack(side="left", padx=5)
        
        self.search_btn = ttk.Button(top_frame, text="🔍 Поиск", command=self.start_search)
        self.search_btn.pack(side="left", padx=5)
        
        # Панель избранного
        fav_frame = ttk.Frame(self)
        fav_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(fav_frame, text="Избранное:").pack(side="left")
        
        self.fav_tree = ttk.Treeview(fav_frame, columns=("login", "name"), show="headings", height=4)
        self.fav_tree.heading("login", text="Логин")
        self.fav_tree.heading("name", text="Имя")
        
        fav_scroll = ttk.Scrollbar(fav_frame, orient="vertical", command=self.fav_tree.yview)
        self.fav_tree.configure(yscrollcommand=fav_scroll.set)
        
        self.fav_tree.pack(side="left", fill="both", expand=True, padx=(0, 5))
        fav_scroll.pack(side="right", fill="y")
        
        # Основная область: Результаты и Аватар
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Левая часть: Таблица результатов
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame)
        
        ttk.Label(left_frame, text="Результаты поиска:").pack(anchor="w")
        
        self.tree = ttk.Treeview(left_frame, columns=("login", "name", "bio"), show="headings")
        self.tree.heading("login", text="Логин")
        self.tree.heading("name", text="Имя")
        self.tree.heading("bio", text="О себе")
        
        self.tree.column("login", width=120, anchor="center")
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("bio", width=350, anchor="w")
        
        tree_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        
        self.tree.pack(fill="both", expand=True, pady=(5, 0))
        tree_scroll.pack(side="right", fill="y")
        
        # Правая часть: Аватар и Кнопка
        right_frame = ttk.Frame(main_pane, width=200)
        main_pane.add(right_frame)
        
        self.avatar_canvas = tk.Canvas(right_frame, width=180, height=180, bg="#f0f0f0")
        self.avatar_canvas.pack(pady=10)
        
        self.add_to_fav_btn = ttk.Button(right_frame, text="⭐ Добавить в избранное", state="disabled", command=self.add_to_favorites)
        self.add_to_fav_btn.pack(pady=5)

    # --- Методы логики ---
    def start_search(self):
        username = self.username_var.get().strip()

        if not username:
            messagebox.showwarning("Ошибка ввода", "Поле поиска не должно быть пустым!")
            return

        # Очистка предыдущих данных
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if hasattr(self, 'avatar_on_canvas'):
            self.avatar_canvas.delete(self.avatar_on_canvas)
            
        self.current_user_data = None
        self.add_to_fav_btn.config(state="disabled")

        self.set_interface_state("disabled")
        
        # Запуск асинхронной задачи
        asyncio.run(self.async_search(username))
    
    async def async_search(self, username):
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": "GitHubUserFinder-Tkinter"}) as session:
                user_data = await fetch_user_data(session, username)
                self.current_user_data = user_data

                # Вставка в таблицу (должно быть в главном потоке)
                self.tree.insert("", "end", values=(
                     user_data['login'],
                     user_data['name'] or "-",
                     user_data['bio'] or "-"
                 ))
                 
                # Отрисовка аватара (должно быть в главном потоке)
                img_resized = user_data['avatar_image'].resize((180, 180), Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(img_resized)
                self.avatar_cache[username] = tk_img # Сохраняем ссылку!
                
                self.avatar_on_canvas = self.avatar_canvas.create_image(90, 90, image=tk_img) # Центр

                self.add_to_fav_btn.config(state="normal")
                 
        except GitHubAPIError as e:
            messagebox.showerror("Ошибка GitHub", str(e))
        except Exception as e:
            messagebox.showerror("Ошибка сети", f"Не удалось подключиться к серверу.\n{str(e)}")
        finally:
            self.set_interface_state("normal")
    
    def set_interface_state(self, state):
        new_state = "disabled" if state == "disabled" else "normal"
        widgets_to_block = [self.entry, self.search_btn]
        
        for widget in widgets_to_block:
            widget.config(state=new_state)
         
        # Кнопку избранного блокируем только если она была активна и мы не в процессе поиска
        if state == "normal" and hasattr(self, 'current_user_data') and self.current_user_data is not None:
            self.add_to_fav_btn.config(state="normal")
        elif state == "disabled":
            self.add_to_fav_btn.config(state="disabled")
    
    def add_to_favorites(self):
        if not self.current_user_data:
            return

        fav_data = load_favorites()
        username = self.current_user_data['login']
        
        if username in fav_data["favorites"]:
            messagebox.showinfo("Уже в избранном", f"Пользователь {username} уже добавлен.")
            return

        fav_data["favorites"].append(username)
        save_favorites(fav_data)
        
        name_for_display = self.current_user_data['name'] or username
        self.fav_tree.insert("", "end", values=(username, name_for_display))
        
        messagebox.showinfo("Успех", f"Пользователь {username} добавлен в избранное.")
    
    def load_favorites_to_tree(self):
        fav_data = load_favorites()
         
        for user_login in fav_data["favorites"]:
            # В реальном приложении можно было бы кэшировать имена,
            # но для простоты здесь показываем только логин.
            self.fav_tree.insert("", "end", values=(user_login, "-"))

if __name__ == "__main__":
    app = GitHubUserFinderApp()
    app.mainloop()