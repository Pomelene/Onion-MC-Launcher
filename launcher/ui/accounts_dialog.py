# -*- coding: utf-8 -*-
"""账号管理对话框：离线账号与微软正版登录。"""

from .dpi import px, geometry
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ..accounts import AccountRecord, offline_uuid, validate_username
from ..auth.microsoft import DeviceCode, login_with_device_code
from .util import center, run_async


class AccountsDialog(tk.Toplevel):
    """查看、添加与切换账号。"""

    def __init__(self, parent, store, config):
        super().__init__(parent)
        self.store = store
        self.config_obj = config
        self.title("账号管理")
        self.geometry(geometry("780x440"))
        self.transient(parent)
        self.grab_set()
        self._build()
        self._refresh()
        center(self, parent)

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        columns = ("name", "type", "uuid")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        self.tree.heading("name", text="账号名")
        self.tree.heading("type", text="类型")
        self.tree.heading("uuid", text="UUID")
        self.tree.column("name", width=160)
        self.tree.column("type", width=80)
        self.tree.column("uuid", width=320)
        self.tree.pack(fill="both", expand=True)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=px((10, 0)))
        ttk.Button(buttons, text="添加离线账号", command=self._add_offline).pack(side="left")
        ttk.Button(buttons, text="微软正版登录", command=self._add_microsoft).pack(side="left", padx=px(6))
        ttk.Button(buttons, text="外置登录", command=self._add_authlib).pack(side="left")
        ttk.Button(buttons, text="设为当前", command=self._set_current).pack(side="left", padx=px(6))
        ttk.Button(buttons, text="删除", command=self._delete).pack(side="right")
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side="right", padx=px(6))

    def _refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for acc in self.store.accounts:
            kind = {"microsoft": "正版", "authlib": "外置"}.get(acc.type, "离线")
            name = acc.username + ("  ← 当前" if acc.uuid == self.store.current_uuid else "")
            self.tree.insert("", "end", iid=acc.uuid, values=(name, kind, acc.uuid))

    def _selected(self) -> str:
        sel = self.tree.selection()
        return sel[0] if sel else ""

    def _add_offline(self) -> None:
        name = simpledialog.askstring("离线账号", "请输入玩家名称：", parent=self)
        if not name:
            return
        name = name.strip()
        error = validate_username(name)
        if error:
            messagebox.showerror("玩家名无效", error, parent=self)
            return
        record = AccountRecord(type="offline", username=name, uuid=offline_uuid(name),
                               access_token="0", user_type="legacy")
        self.store.add(record)
        self.store.set_current(record.uuid)
        self._refresh()

    def _add_authlib(self) -> None:
        server = simpledialog.askstring("外置登录", "验证服务器地址（https://…）：", parent=self,
                                        initialvalue=self.config_obj.get("authlib_url") or "")
        if not server:
            return
        from urllib.parse import urlparse
        parsed = urlparse(server.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            messagebox.showerror("地址无效", "请输入有效的 HTTPS 验证服务器地址。", parent=self)
            return
        email = simpledialog.askstring("外置登录", "邮箱或用户名：", parent=self)
        if not email:
            return
        password = simpledialog.askstring("外置登录", "密码（仅用于本次登录，不保存）：", show="*", parent=self)
        if not password:
            return
        from ..auth.authlib import authenticate
        def done(data):
            record = AccountRecord(type="authlib", **data)
            self.store.add(record)
            self.store.set_current(record.uuid)
            self._refresh()
        run_async(self, lambda: authenticate(server, email, password), on_success=done,
                  on_error=lambda e: messagebox.showerror("登录失败", str(e), parent=self))

    def _add_microsoft(self) -> None:
        client_id = (self.config_obj.get("microsoft_client_id") or "").strip()
        if not client_id:
            messagebox.showinfo(
                "需要配置",
                "微软登录需要 Azure 应用的 client_id。\n请先在“设置”中填写后再试。",
                parent=self)
            return
        LoginWindow(self, client_id, self._on_microsoft_success)

    def _on_microsoft_success(self, data: dict) -> None:
        record = AccountRecord(
            type="microsoft",
            username=data["username"],
            uuid=data["uuid"],
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=data.get("expires_at", 0.0),
            client_id=(self.config_obj.get("microsoft_client_id") or "").strip(),
            user_type="msa",
            xuid=data.get("xuid", ""),
        )
        self.store.add(record)
        self.store.set_current(record.uuid)
        self._refresh()

    def _set_current(self) -> None:
        uuid = self._selected()
        if uuid:
            self.store.set_current(uuid)
            self._refresh()

    def _delete(self) -> None:
        uuid = self._selected()
        if not uuid:
            return
        if messagebox.askyesno("确认", "确定删除该账号吗？", parent=self):
            self.store.remove(uuid)
            self._refresh()


class LoginWindow(tk.Toplevel):
    """微软设备码登录窗口。"""

    def __init__(self, parent, client_id: str, on_success):
        super().__init__(parent)
        self.client_id = client_id
        self.on_success = on_success
        self._cancelled = False
        self.title("微软正版登录")
        self.geometry(geometry("520x260"))
        self.transient(parent)
        self.grab_set()

        self.status_var = tk.StringVar(value="正在请求设备码……")
        self.code_var = tk.StringVar(value="")
        self.url_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, padding=(14, 12)).pack(anchor="w")
        ttk.Label(self, textvariable=self.code_var, font=("Consolas", 20),
                  padding=(14, 0), foreground="#1a5fb4").pack(anchor="w")
        ttk.Label(self, textvariable=self.url_var, padding=(14, 8),
                  foreground="#1a5fb4").pack(anchor="w")
        ttk.Label(self, text="在浏览器中打开上面的网址并输入代码，完成后本窗口会自动关闭。",
                  padding=(14, 0), foreground="#666").pack(anchor="w")
        ttk.Button(self, text="取消", command=self._cancel).pack(side="bottom", pady=px(10))
        center(self, parent)

        run_async(self, self._login, on_success=self._done, on_error=self._failed)

    def _login(self) -> dict:
        def on_code(code: DeviceCode) -> None:
            self.after(0, lambda: self._show_code(code))

        def on_step(text: str) -> None:
            self.after(0, lambda: self.status_var.set(text))

        return login_with_device_code(
            self.client_id, on_code, lambda: self._cancelled, on_step)

    def _show_code(self, code: DeviceCode) -> None:
        self.code_var.set(code.user_code)
        self.url_var.set(code.verification_uri)
        self.status_var.set("等待浏览器授权……")

    def _done(self, data: dict) -> None:
        self.on_success(data)
        self.destroy()

    def _failed(self, exc: Exception) -> None:
        messagebox.showerror("登录失败", str(exc), parent=self)
        self.destroy()

    def _cancel(self) -> None:
        self._cancelled = True
        self.destroy()
