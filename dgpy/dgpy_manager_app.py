"""DG Script Manager window (P4: uninstall, changelog, shared-path checks)."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import dgpy_config
import dgpy_flame_util
import dgpy_gui
import dgpy_log
import dgpy_manifest
import dgpy_paths
import dgpy_sync

__version__ = "0.3.18"

_WINDOW: QtWidgets.QWidget | None = None


class ManagerWindow(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DG Script Manager")
        self.resize(900, 600)
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowMinMaxButtonsHint
        )

        self._logger = dgpy_log.setup()
        self._cfg = dgpy_config.load()
        self._rows: list[dgpy_sync.PackageRow] = []
        self._manifest: dgpy_manifest.Manifest | None = None
        self._verify_issues: list[dgpy_sync.VerifyIssue] = []
        self._warn_once = False

        root = self._cfg.resolved_install_root()
        kind = dgpy_paths.detect_parent_kind(root)
        writable, write_msg = dgpy_paths.check_writable(root)

        layout = QtWidgets.QVBoxLayout(self)

        self._info = QtWidgets.QLabel()
        self._info.setWordWrap(True)
        self._info.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._info)
        self._update_info_label(root, kind, writable, write_msg)

        channel_row = QtWidgets.QHBoxLayout()
        channel_row.addWidget(QtWidgets.QLabel("Channel:"))
        self._channel = QtWidgets.QComboBox()
        self._channel.addItems(["latest", "stable", "dev"])
        idx = self._channel.findText(self._cfg.channel)
        self._channel.setCurrentIndex(idx if idx >= 0 else 0)
        self._channel.currentTextChanged.connect(self._on_channel_changed)
        channel_row.addWidget(self._channel)
        channel_row.addStretch(1)
        layout.addLayout(channel_row)

        toolbar = QtWidgets.QHBoxLayout()
        self._btn_refresh = QtWidgets.QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self.refresh_table)
        toolbar.addWidget(self._btn_refresh)

        self._btn_install = QtWidgets.QPushButton("Install / Update Selected")
        self._btn_install.clicked.connect(self.install_selected)
        toolbar.addWidget(self._btn_install)

        self._btn_all = QtWidgets.QPushButton("Update All")
        self._btn_all.clicked.connect(self.install_all)
        toolbar.addWidget(self._btn_all)

        self._btn_verify = QtWidgets.QPushButton("Verify…")
        self._btn_verify.setToolTip(
            "Compare local files to GitHub manifest (including sha256)"
        )
        self._btn_verify.clicked.connect(self.verify_install)
        toolbar.addWidget(self._btn_verify)

        self._btn_repair_sel = QtWidgets.QPushButton("Repair Selected")
        self._btn_repair_sel.setToolTip(
            "Re-download selected packages that Verify flagged (or New/Update)"
        )
        self._btn_repair_sel.clicked.connect(self.repair_selected)
        toolbar.addWidget(self._btn_repair_sel)

        self._btn_repair_all = QtWidgets.QPushButton("Repair All Issues")
        self._btn_repair_all.setToolTip(
            "Re-download packages with Verify issues (skips manual-only New)"
        )
        self._btn_repair_all.clicked.connect(self.repair_all_issues)
        toolbar.addWidget(self._btn_repair_all)

        self._btn_uninstall = QtWidgets.QPushButton("Uninstall Selected")
        self._btn_uninstall.clicked.connect(self.uninstall_selected)
        toolbar.addWidget(self._btn_uninstall)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._table = QtWidgets.QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Name", "Installed", "Remote", "Status", "Id"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setColumnHidden(4, True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table, stretch=2)

        layout.addWidget(QtWidgets.QLabel("Details / Changelog"))
        self._detail = QtWidgets.QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumBlockCount(400)
        layout.addWidget(self._detail, stretch=1)

        layout.addWidget(QtWidgets.QLabel("Log"))
        self._log_view = QtWidgets.QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(800)
        layout.addWidget(self._log_view, stretch=1)

        note = QtWidgets.QLabel(
            "Install 後は自動 Rescan。core/manager は Uninstall 不可"
            "（配布基盤のため）。移行期間メニュー: DGpy → DG Script Manager"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        dgpy_log.add_listener(self._append_log)
        self.refresh_table()
        self._logger.info("Manager opened (P4)")
        QtCore.QTimer.singleShot(0, self._show_startup_warnings)

    def _update_info_label(
        self, root, kind: str, writable: bool, write_msg: str
    ) -> None:
        manifest_url = dgpy_manifest.default_manifest_url(self._cfg)
        write_state = "writable" if writable else "READ-ONLY"
        effective_repo = dgpy_manifest.repo_for_channel(self._cfg)
        text = (
            f"Install root: {root}  [{kind}, {write_state}]\n"
            f"Channel: {self._cfg.channel}  |  Repo: {effective_repo}\n"
            f"Manifest: {manifest_url}"
        )
        if self._cfg.channel == "dev":
            import dgpy_prefs

            text += f"\nDev token: {dgpy_prefs.token_status_label()}"
        if not writable and write_msg:
            text += f"\n⚠ {write_msg}"
        self._info.setText(text)

    def _show_startup_warnings(self) -> None:
        if self._warn_once:
            return
        self._warn_once = True
        root = self._cfg.resolved_install_root()
        ok, msg = dgpy_paths.check_writable(root)
        if not ok:
            dgpy_gui.warning(self, "DG Script Manager", msg)
        dup = dgpy_paths.duplicate_dgpy_warning(root)
        if dup:
            dgpy_gui.warning(self, "DG Script Manager", dup)

    def _on_channel_changed(self, channel: str) -> None:
        if not channel or channel == self._cfg.channel:
            return
        self._cfg.channel = channel
        dgpy_config.save(self._cfg)
        self._logger.info("Channel set to %s", channel)
        self.refresh_table()

    def _append_log(self, message: str) -> None:
        self._log_view.appendPlainText(message)

    def _set_busy(self, busy: bool) -> None:
        for btn in (
            self._btn_refresh,
            self._btn_install,
            self._btn_all,
            self._btn_verify,
            self._btn_repair_sel,
            self._btn_repair_all,
            self._btn_uninstall,
            self._channel,
        ):
            btn.setEnabled(not busy)
        if busy:
            QtWidgets.QApplication.setOverrideCursor(
                QtGui.QCursor(QtCore.Qt.CursorShape.WaitCursor)
            )
        else:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _ensure_writable(self) -> bool:
        ok, msg = dgpy_paths.check_writable(self._cfg.resolved_install_root())
        if not ok:
            dgpy_gui.error(self, "DG Script Manager", msg)
            return False
        return True

    def refresh_table(self) -> None:
        self._set_busy(True)
        try:
            self._cfg = dgpy_config.load()
            root = self._cfg.resolved_install_root()
            kind = dgpy_paths.detect_parent_kind(root)
            writable, write_msg = dgpy_paths.check_writable(root)
            self._update_info_label(root, kind, writable, write_msg)
            try:
                self._manifest = dgpy_manifest.fetch_manifest(self._cfg)
                self._rows = dgpy_sync.compare(self._manifest, root)
                self._logger.info(
                    "Manifest OK (%s packages, channel=%s)",
                    len(self._manifest.packages),
                    self._manifest.channel,
                )
            except Exception as exc:  # noqa: BLE001
                self._manifest = None
                self._rows = []
                self._logger.error("Manifest fetch failed: %s", exc)
                dgpy_gui.warning(
                    self,
                    "DG Script Manager",
                    f"マニフェストを取得できませんでした。\n{exc}\n\n"
                    "channel=dev は Private -dev 用です。"
                    "DGpy → Preferences… で GitHub token を設定してください。\n"
                    "channel=stable は tag/branch が必要です。"
                    "通常は channel=latest を使います。",
                )

            self._table.setRowCount(len(self._rows))
            for i, row in enumerate(self._rows):
                self._table.setItem(i, 0, QtWidgets.QTableWidgetItem(row.name))
                self._table.setItem(i, 1, QtWidgets.QTableWidgetItem(row.installed))
                self._table.setItem(i, 2, QtWidgets.QTableWidgetItem(row.remote))
                self._table.setItem(i, 3, QtWidgets.QTableWidgetItem(row.status))
                self._table.setItem(i, 4, QtWidgets.QTableWidgetItem(row.package_id))
            self._on_selection_changed()
        finally:
            self._set_busy(False)

    def _selected_rows(self) -> list[dgpy_sync.PackageRow]:
        ids: set[str] = set()
        for idx in self._table.selectionModel().selectedRows():
            item = self._table.item(idx.row(), 4)
            if item:
                ids.add(item.text())
        return [r for r in self._rows if r.package_id in ids]

    def _on_selection_changed(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self._detail.setPlainText("行を選択すると summary / changelog を表示します。")
            return
        blocks: list[str] = []
        for row in rows:
            pkg = row.remote_pkg
            blocks.append(f"## {row.name} ({row.package_id})")
            blocks.append(f"Status: {row.status}  |  Installed: {row.installed}  |  Remote: {row.remote}")
            if pkg:
                if pkg.summary:
                    blocks.append(f"Summary: {pkg.summary}")
                if not pkg.auto_install:
                    blocks.append(
                        "Install policy: manual only while New "
                        "(skipped by Update All / startup auto-update)."
                    )
                if pkg.depends:
                    blocks.append("Depends: " + ", ".join(pkg.depends))
                if pkg.changelog:
                    blocks.append("Changelog:\n" + pkg.changelog)
                else:
                    blocks.append("Changelog: (none)")
            else:
                blocks.append("(remote package info unavailable — Local only)")
            blocks.append("")
        self._detail.setPlainText("\n".join(blocks))

    def install_selected(self) -> None:
        rows = [
            r
            for r in self._selected_rows()
            if r.status in (dgpy_sync.STATUS_NEW, dgpy_sync.STATUS_UPDATE)
            and r.remote_pkg
        ]
        if not rows:
            dgpy_gui.info(
                self,
                "DG Script Manager",
                "Install / Update 対象の行を選んでください（New または Update）。",
            )
            return
        self._run_install([r.remote_pkg for r in rows if r.remote_pkg])

    def install_all(self) -> None:
        try:
            rows = dgpy_sync.actionable(self._rows)
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Update All failed: %s", exc)
            dgpy_gui.error(self, "DG Script Manager", f"Update All failed:\n{exc}")
            return
        if not rows:
            dgpy_gui.info(
                self,
                "DG Script Manager",
                "更新・新規インストール対象はありません。",
            )
            return
        self._run_install([r.remote_pkg for r in rows if r.remote_pkg])

    def verify_install(self) -> None:
        self._set_busy(True)
        try:
            self._cfg = dgpy_config.load()
            try:
                self._manifest = dgpy_manifest.fetch_manifest(self._cfg)
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Verify: manifest fetch failed: %s", exc)
                dgpy_gui.warning(
                    self,
                    "DG Script Manager",
                    f"マニフェストを取得できませんでした。\n{exc}",
                )
                return
            root = self._cfg.resolved_install_root()
            self._verify_issues = dgpy_sync.verify_install(self._manifest, root)
            report = dgpy_sync.format_verify_report(self._verify_issues)
            self._detail.setPlainText(report)
            self._logger.info(
                "Verify done: %s issue(s) channel=%s",
                len(self._verify_issues),
                self._cfg.channel,
            )
            # Refresh status column (missing files still show as Update).
            self._rows = dgpy_sync.compare(self._manifest, root)
            self._table.setRowCount(len(self._rows))
            for i, row in enumerate(self._rows):
                self._table.setItem(i, 0, QtWidgets.QTableWidgetItem(row.name))
                self._table.setItem(i, 1, QtWidgets.QTableWidgetItem(row.installed))
                self._table.setItem(i, 2, QtWidgets.QTableWidgetItem(row.remote))
                self._table.setItem(i, 3, QtWidgets.QTableWidgetItem(row.status))
                self._table.setItem(i, 4, QtWidgets.QTableWidgetItem(row.package_id))

            if not self._verify_issues:
                dgpy_gui.info(
                    self,
                    "DG Script Manager",
                    f"Verify OK.\n"
                    f"{len(self._manifest.packages)} package(s) match "
                    f"channel={self._cfg.channel}.",
                )
                return

            n_pkg = len({i.package_id for i in self._verify_issues})
            preview = report
            if len(preview) > 2500:
                preview = preview[:2500] + "\n…"
            if dgpy_gui.confirm(
                self,
                "DG Script Manager",
                f"Verify: {len(self._verify_issues)} issue(s) "
                f"in {n_pkg} package(s).\n\n{preview}\n\n"
                "Repair All Issues now?",
            ):
                self._repair_from_issues(
                    include_missing_manual=False, ask_confirm=False
                )
        finally:
            self._set_busy(False)

    def repair_selected(self) -> None:
        if self._manifest is None:
            dgpy_gui.info(
                self,
                "DG Script Manager",
                "先に Refresh または Verify… を実行してください。",
            )
            return
        selected = {r.package_id for r in self._selected_rows()}
        if not selected:
            dgpy_gui.info(
                self, "DG Script Manager", "Repair する行を選んでください。"
            )
            return
        issues = [
            i for i in self._verify_issues if i.package_id in selected
        ]
        # Also treat New/Update selection as repairable without prior Verify.
        for row in self._selected_rows():
            if (
                row.remote_pkg
                and row.status
                in (dgpy_sync.STATUS_NEW, dgpy_sync.STATUS_UPDATE)
                and row.package_id not in {i.package_id for i in issues}
            ):
                issues.append(
                    dgpy_sync.VerifyIssue(
                        package_id=row.package_id,
                        code=(
                            dgpy_sync.ISSUE_MISSING_PACKAGE
                            if row.status == dgpy_sync.STATUS_NEW
                            else dgpy_sync.ISSUE_VERSION_BEHIND
                        ),
                        detail=f"status={row.status}",
                    )
                )
        if not issues:
            dgpy_gui.info(
                self,
                "DG Script Manager",
                "選択行に Verify の問題も New/Update もありません。\n"
                "先に Verify… を実行するか、New/Update 行を選んでください。",
            )
            return
        self._repair_from_issues(
            issues=issues, include_missing_manual=True
        )

    def repair_all_issues(self) -> None:
        if not self._verify_issues:
            dgpy_gui.info(
                self,
                "DG Script Manager",
                "修復対象がありません。先に Verify… を実行してください。",
            )
            return
        self._repair_from_issues(include_missing_manual=False)

    def _repair_from_issues(
        self,
        *,
        issues: list[dgpy_sync.VerifyIssue] | None = None,
        include_missing_manual: bool,
        ask_confirm: bool = True,
    ) -> None:
        if self._manifest is None:
            return
        issues = issues if issues is not None else self._verify_issues
        packages = dgpy_sync.packages_for_repair(
            issues,
            self._manifest,
            include_missing_manual=include_missing_manual,
        )
        if not packages:
            dgpy_gui.info(
                self,
                "DG Script Manager",
                "Repair 対象のパッケージがありません"
                "（manual-only New は Repair All から除外されます）。",
            )
            return
        names = ", ".join(p.name for p in packages)
        if ask_confirm and not dgpy_gui.confirm(
            self,
            "DG Script Manager",
            f"次を再インストール（Repair）しますか？\n\n{names}",
        ):
            return
        self._run_install(packages)

    def uninstall_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            dgpy_gui.info(self, "DG Script Manager", "Uninstall する行を選んでください。")
            return

        protected = [r for r in rows if r.package_id in dgpy_sync.PROTECTED_PACKAGES]
        apps = [r for r in rows if r.package_id not in dgpy_sync.PROTECTED_PACKAGES]
        if protected and not apps:
            dgpy_gui.warning(
                self,
                "DG Script Manager",
                "core / manager は Uninstall できません。\n"
                "完全削除する場合は dgpy/ フォルダ自体を手動で削除してください。",
            )
            return
        if protected:
            dgpy_gui.warning(
                self,
                "DG Script Manager",
                "選択に core/manager が含まれています。それらはスキップし、"
                "アプリのみ削除します。",
            )
        if not apps:
            return

        names = ", ".join(r.name for r in apps)
        if not dgpy_gui.confirm(
            self,
            "DG Script Manager",
            f"次を Uninstall しますか？\n\n{names}\n\n"
            "dgpy/apps 配下のファイルが削除されます。",
        ):
            return
        if not self._ensure_writable():
            return

        self._set_busy(True)
        try:
            done = dgpy_sync.uninstall_many(
                [r.package_id for r in apps],
                root=self._cfg.resolved_install_root(),
            )
            rescanned = dgpy_flame_util.rescan_python_hooks()
            msg = "Uninstall 完了: " + ", ".join(done)
            if rescanned:
                msg += "\n\nRescan Python Hooks を実行しました。"
            dgpy_gui.info(self, "DG Script Manager", msg)
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Uninstall failed: %s", exc)
            dgpy_gui.error(self, "DG Script Manager", f"Uninstall failed:\n{exc}")
        finally:
            self._set_busy(False)
            self.refresh_table()

    def _expand_dependencies(self, packages: list) -> list:
        if not self._manifest:
            return list(packages)
        return dgpy_sync.expand_dependencies(packages, self._manifest, self._rows)

    def _run_install(self, packages) -> None:
        """Install in phases; show dialogs (manual path)."""
        if not self._ensure_writable():
            return
        self._set_busy(True)
        try:
            packages = self._expand_dependencies(packages)
            result = dgpy_sync.run_phased_install(
                packages, root=self._cfg.resolved_install_root()
            )
            if result.skipped:
                dgpy_gui.warning(self, "DG Script Manager", result.skipped)
                return
            if result.error:
                partial = (
                    f"\n\n完了済み: {', '.join(result.done)}" if result.done else ""
                )
                dgpy_gui.error(
                    self,
                    "DG Script Manager",
                    f"Install failed:\n{result.error}{partial}",
                )
                return

            updated_self = any(pid in ("core", "manager") for pid in result.done)
            msg = "インストール完了: " + (
                ", ".join(result.done) if result.done else "(なし)"
            )
            msg += "\n\n"
            if result.rescans:
                msg += (
                    "Rescan Python Hooks を実行しました"
                    f"（{' → '.join(result.rescans)}）。"
                )
            elif result.done:
                msg += (
                    "自動 Rescan に失敗したか、Flame 外のためスキップしました。\n"
                    "手動で Python → Rescan Python Hooks を実行してください。"
                )
            if updated_self:
                msg += (
                    "\n\ncore / manager を更新した場合は、"
                    "Flame の再起動を推奨します。"
                )
            dgpy_gui.info(self, "DG Script Manager", msg)
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Install failed: %s", exc)
            dgpy_gui.error(
                self,
                "DG Script Manager",
                f"Install failed:\n{exc}",
            )
        finally:
            self._set_busy(False)
            self.refresh_table()

    def closeEvent(self, event) -> None:  # noqa: N802
        dgpy_log.remove_listener(self._append_log)
        try:
            QtWidgets.QApplication.restoreOverrideCursor()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)


def open_manager(_selection=None) -> None:
    global _WINDOW
    dgpy_paths.ensure_dgpy_on_sys_path()
    dgpy_log.setup()
    import dgpy_local_inventory

    dgpy_local_inventory.ensure_seed_installed()
    try:
        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication([])
    except Exception as exc:  # noqa: BLE001
        dgpy_log.get_logger().error("Qt application unavailable: %s", exc)
        return

    if _WINDOW is not None:
        try:
            if _WINDOW.isVisible():
                _WINDOW.raise_()
                _WINDOW.activateWindow()
                return
        except RuntimeError:
            _WINDOW = None

    try:
        _WINDOW = ManagerWindow()
        _WINDOW.show()
        _WINDOW.raise_()
        _WINDOW.activateWindow()
    except Exception as exc:  # noqa: BLE001
        dgpy_log.get_logger().exception("Failed to open Manager: %s", exc)
        dgpy_gui.error(None, "DG Script Manager", f"Failed to open:\n{exc}")
