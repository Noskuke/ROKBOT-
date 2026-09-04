import asyncio
import functools
import io
import os
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_TOKEN, VPS_IP
from utils_gui import (
    do_action_check,
    do_action_off,
    do_action_on,
    find_account_dots_for_check,
    focus_game_window,
    get_game_window,
)
from web_server import (
    close_remote_session,
    open_remote_session,
    remote_session_owner,
    remote_session_url,
)
from utils_user import (
    get_acc_for_user,
    is_admin_user,
    normalize_account_name,
    save_admin_user,
    save_user_account,
)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
control_lock = asyncio.Lock()
active_controller = None


async def is_bot_admin(interaction: discord.Interaction):
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(getattr(permissions, "administrator", False)) or is_admin_user(interaction.user.id)


admin_only = app_commands.check(is_bot_admin)


def normalize_admin_account(acc_name):
    account_name = normalize_account_name(acc_name)
    if not account_name or not account_name.isdigit():
        return None
    return account_name if int(account_name) >= 1 else None


def control_required(command):
    @functools.wraps(command)
    async def guarded_command(interaction, *args, **kwargs):
        global active_controller

        if control_lock.locked():
            controller = active_controller or "người dùng khác"
            await interaction.response.send_message(
                f"⏳ Có **{controller}** đang điều khiển, vui lòng đợi.",
                ephemeral=True,
            )
            return

        await control_lock.acquire()
        active_controller = interaction.user.display_name
        try:
            return await command(interaction, *args, **kwargs)
        finally:
            active_controller = None
            control_lock.release()

    return guarded_command


async def _send_check_attachment(interaction: discord.Interaction, result, filename: str, account_name: str = None):
    if result is None:
        await interaction.followup.send("❌ Không chụp được ảnh.", ephemeral=True)
        return False

    content = f"👤 Tài khoản: {account_name}" if account_name else None

    try:
        if hasattr(result, "getvalue"):
            payload = io.BytesIO(result.getvalue())
            await interaction.followup.send(content=content, file=discord.File(payload, filename=filename), ephemeral=True)
            return True

        if hasattr(result, "seek"):
            result.seek(0)
            if hasattr(result, "read"):
                await interaction.followup.send(content=content, file=discord.File(result, filename=filename), ephemeral=True)
                return True

        if isinstance(result, str) and os.path.exists(result):
            with open(result, "rb") as fp:
                await interaction.followup.send(content=content, file=discord.File(fp, filename=os.path.basename(result)), ephemeral=True)
                return True
    except Exception:
        pass

    await interaction.followup.send(content=content or "❌ Không chụp được ảnh.", ephemeral=True)
    return False


@bot.event
async def on_ready():
    print(f"🤖 Bot Discord đã trực tuyến: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Đã đồng bộ {len(synced)} lệnh Slash Commands.")

        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        print(f"⚡ Đã đồng bộ lệnh theo {len(bot.guilds)} server.")
    except Exception as exc:
        print(f"Lỗi đồng bộ lệnh: {exc}")


@bot.tree.command(name="use", description="Lấy link giao diện Web Remote")
@control_required
async def cmd_use(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not get_game_window():
        await interaction.followup.send("❌ Game chưa khởi động! Vui lòng mở Rise of Kingdoms trước.", ephemeral=True)
        return

    target_acc = get_acc_for_user(interaction.user.id)
    if not target_acc:
        await interaction.followup.send(
            "❌ Bạn chưa được Admin cấp tài khoản mặc định để điều khiển.",
            ephemeral=True,
        )
        return

    if not focus_game_window():
        await interaction.followup.send("❌ Không thể bật cửa sổ game.", ephemeral=True)
        return

    active_owner = remote_session_owner()
    if active_owner:
        await interaction.followup.send(
            f"⏳ Có **{active_owner}** đang dùng Web Remote, vui lòng đợi.",
            ephemeral=True,
        )
        return

    try:
        x_coord, y_coord = await asyncio.wait_for(
            asyncio.to_thread(find_account_dots_for_check, target_acc),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        await interaction.followup.send("⏱️ Không thể chọn tài khoản trong 30 giây.", ephemeral=True)
        return
    except Exception as exc:
        await interaction.followup.send(f"❌ Lỗi chọn tài khoản: {str(exc)[:100]}", ephemeral=True)
        return

    if x_coord is None or y_coord is None:
        await interaction.followup.send(
            f"❌ Không tìm thấy tài khoản **{target_acc}** trong danh sách.",
            ephemeral=True,
        )
        return

    session_token, active_owner = open_remote_session(
        interaction.user.display_name,
        target_acc,
        interaction.user.id,
    )
    if not session_token:
        await interaction.followup.send(
            f"⏳ Có **{active_owner}** đang dùng Web Remote, vui lòng đợi.",
            ephemeral=True,
        )
        return

    if interaction.channel:
        await interaction.channel.send(
            f"🎮 **{interaction.user.display_name}** đang sử dụng tài khoản **{target_acc}**. "
            "Vui lòng đợi.",
            silent=True,
        )

    await interaction.followup.send(
        f"🌐 Tài khoản **{target_acc}** đã được chọn. Truy cập Web Remote tại: "
        f"{remote_session_url(VPS_IP, session_token)}",
        ephemeral=True,
    )


@bot.tree.command(name="use_admin", description="[ADMIN] Mở Web Remote cho bất kỳ tài khoản nào")
@admin_only
@control_required
async def cmd_use_admin(interaction: discord.Interaction, acc_name: str):
    await interaction.response.defer(ephemeral=True)
    target_acc = normalize_admin_account(acc_name)
    if not target_acc:
        await interaction.followup.send(
            "❌ Tài khoản phải là số lớn hơn hoặc bằng 1.",
            ephemeral=True,
        )
        return

    if not get_game_window():
        await interaction.followup.send("❌ Game chưa khởi động!", ephemeral=True)
        return

    if not focus_game_window():
        await interaction.followup.send("❌ Không thể bật cửa sổ game.", ephemeral=True)
        return

    active_owner = remote_session_owner()
    if active_owner:
        await interaction.followup.send(
            f"⏳ Có **{active_owner}** đang dùng Web Remote, vui lòng đợi.",
            ephemeral=True,
        )
        return

    try:
        x_coord, y_coord = await asyncio.wait_for(
            asyncio.to_thread(find_account_dots_for_check, target_acc),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        await interaction.followup.send("⏱️ Không thể chọn tài khoản trong 30 giây.", ephemeral=True)
        return

    if x_coord is None or y_coord is None:
        await interaction.followup.send(f"❌ Không tìm thấy tài khoản **{target_acc}**.", ephemeral=True)
        return

    session_token, active_owner = open_remote_session(
        interaction.user.display_name,
        target_acc,
        interaction.user.id,
    )
    if not session_token:
        await interaction.followup.send(f"⏳ Có **{active_owner}** đang dùng Web Remote.", ephemeral=True)
        return

    await interaction.followup.send(
        f"🌐 Đã chọn tài khoản **{target_acc}**: {remote_session_url(VPS_IP, session_token)}",
        ephemeral=True,
    )


@bot.tree.command(name="done", description="Kết thúc phiên Web Remote hiện tại")
async def cmd_done(interaction: discord.Interaction):
    closed, active_owner = close_remote_session(interaction.user.id)
    if not closed:
        if active_owner:
            await interaction.response.send_message(
                f"⏳ **{active_owner}** đang sử dụng Web Remote, chỉ người đó mới có thể kết thúc phiên.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "ℹ️ Hiện không có phiên Web Remote nào đang hoạt động.",
                ephemeral=True,
            )
        return

    if interaction.channel:
        await interaction.channel.send(
            f"✅ **{interaction.user.display_name}** đã kết thúc phiên Web Remote.",
            silent=True,
        )
    await interaction.response.send_message(
        "✅ Đã kết thúc phiên Web Remote. Người khác có thể sử dụng.",
        ephemeral=True,
    )


@bot.tree.command(name="add_user", description="[ADMIN] Gán tài khoản game cho thành viên Discord")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    user="Chọn thành viên Discord cần cấp tài khoản",
    account_number="Nhập số thứ tự tài khoản trong danh sách game",
)
async def cmd_add_user(
    interaction: discord.Interaction,
    user: discord.Member,
    account_number: int,
):
    if account_number < 1:
        await interaction.response.send_message(
            "❌ Số tài khoản phải lớn hơn hoặc bằng **1**.",
            ephemeral=True,
        )
        return

    account_name = normalize_account_name(account_number)
    save_user_account(str(user.id), account_name)

    embed = discord.Embed(
        title="👑 [ADMIN] THÊM THÀNH CÔNG",
        description=(
            f"✅ **Thành viên:** {user.mention}\n"
            f"🆔 **Discord ID:** `{user.id}`\n"
            f"🎮 **Tài khoản game:** `{account_name}` (dòng {account_number})\n\n"
            f"Dữ liệu đã được lưu vĩnh viễn!"
        ),
        color=0x2b2d31,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="put", description="[ADMIN CHÍNH] Cấp quyền quản trị bot cho thành viên")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="Chọn thành viên Discord cần cấp quyền Admin")
async def cmd_put(interaction: discord.Interaction, user: discord.Member):
    save_admin_user(user.id)
    await interaction.response.send_message(
        f"✅ Đã cấp quyền Admin bot cho {user.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="ban", description="[ADMIN] Cấm thành viên khỏi server")
@admin_only
@app_commands.describe(user="Chọn thành viên cần ban", reason="Lý do ban")
async def cmd_ban(interaction: discord.Interaction, user: discord.Member, reason: str = "Không nêu lý do"):
    if not interaction.guild:
        await interaction.response.send_message("❌ Lệnh này chỉ dùng được trong server.", ephemeral=True)
        return

    try:
        await interaction.guild.ban(user, reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Bot không có quyền ban thành viên này.", ephemeral=True)
        return

    await interaction.response.send_message(
        f"✅ Đã ban {user.mention}. Lý do: {reason}",
        ephemeral=True,
    )


@cmd_add_user.error
async def cmd_add_user_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Bạn không có quyền **Administrator** để sử dụng lệnh này!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Đã xảy ra lỗi khi thực thi lệnh.", ephemeral=True)


@bot.tree.command(name="on", description="Bật chạy tài khoản")
@control_required
async def cmd_on(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        if not get_game_window():
            await interaction.followup.send(
                "❌ Game chưa khởi động! Vui lòng mở Rise of Kingdoms trước."
            )
            return

        target_acc = get_acc_for_user(interaction.user.id)
        if not target_acc:
            await interaction.followup.send(
                "❌ Bạn chưa được Admin cấp tài khoản mặc định! Vui lòng dùng lệnh kèm tên nick hoặc liên hệ Admin."
            )
            return

        start = time.time()
        _, msg = await asyncio.wait_for(
            asyncio.to_thread(do_action_on, target_acc),
            timeout=30.0
        )
        elapsed = time.time() - start
        
        await interaction.followup.send(content=f"{msg}\n⏱️ ({elapsed:.1f}s)")
        
    except asyncio.TimeoutError:
        await interaction.followup.send(
            content="⏱️ **Timeout!** Thao tác quá lâu (>30s). Vui lòng kiểm tra game và thử lại."
        )
    except Exception as e:
        error_msg = str(e)[:100]
        await interaction.followup.send(
            content=f"❌ Lỗi: {error_msg}"
        )


@bot.tree.command(name="on_admin", description="[ADMIN] Bật bất kỳ tài khoản nào")
@admin_only
@control_required
async def cmd_on_admin(interaction: discord.Interaction, acc_name: str):
    await interaction.response.defer(ephemeral=True)
    target_acc = normalize_admin_account(acc_name)
    if not target_acc:
        await interaction.followup.send("❌ Tài khoản phải là số lớn hơn hoặc bằng 1.", ephemeral=True)
        return
    if not get_game_window():
        await interaction.followup.send("❌ Game chưa khởi động!", ephemeral=True)
        return

    try:
        _, message = await asyncio.wait_for(
            asyncio.to_thread(do_action_on, target_acc),
            timeout=30.0,
        )
        await interaction.followup.send(message, ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⏱️ Thao tác quá lâu (>30s).", ephemeral=True)
    except Exception as exc:
        await interaction.followup.send(f"❌ Lỗi: {str(exc)[:100]}", ephemeral=True)


@bot.tree.command(name="off", description="Tắt và đóng tab tài khoản")
@control_required
async def cmd_off(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        if not get_game_window():
            await interaction.followup.send(
                "❌ Game chưa khởi động! Vui lòng mở Rise of Kingdoms trước."
            )
            return

        target_acc = get_acc_for_user(interaction.user.id)
        if not target_acc:
            await interaction.followup.send(
                "❌ Bạn chưa được Admin cấp tài khoản mặc định! Vui lòng dùng lệnh kèm tên nick hoặc liên hệ Admin."
            )
            return

        start = time.time()
        _, msg = await asyncio.wait_for(
            asyncio.to_thread(do_action_off, target_acc),
            timeout=30.0
        )
        elapsed = time.time() - start
        
        await interaction.followup.send(content=f"{msg}\n⏱️ ({elapsed:.1f}s)")
        
    except asyncio.TimeoutError:
        await interaction.followup.send(
            content="⏱️ **Timeout!** Thao tác quá lâu (>30s). Vui lòng thử lại."
        )
    except Exception as e:
        error_msg = str(e)[:100]
        await interaction.followup.send(
            content=f"❌ Lỗi: {error_msg}"
        )


@bot.tree.command(name="off_admin", description="[ADMIN] Tắt bất kỳ tài khoản nào")
@admin_only
@control_required
async def cmd_off_admin(interaction: discord.Interaction, acc_name: str):
    await interaction.response.defer(ephemeral=True)
    target_acc = normalize_admin_account(acc_name)
    if not target_acc:
        await interaction.followup.send("❌ Tài khoản phải là số lớn hơn hoặc bằng 1.", ephemeral=True)
        return
    if not get_game_window():
        await interaction.followup.send("❌ Game chưa khởi động!", ephemeral=True)
        return

    try:
        _, message = await asyncio.wait_for(
            asyncio.to_thread(do_action_off, target_acc),
            timeout=30.0,
        )
        await interaction.followup.send(message, ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⏱️ Thao tác quá lâu (>30s).", ephemeral=True)
    except Exception as exc:
        await interaction.followup.send(f"❌ Lỗi: {str(exc)[:100]}", ephemeral=True)


@bot.tree.command(name="check", description="Kiểm tra trạng thái tài khoản")
@control_required
async def cmd_check(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if not get_game_window():
            await interaction.followup.send("❌ Game chưa khởi động!", ephemeral=True)
            return

        focus_game_window()

        target_acc = get_acc_for_user(interaction.user.id)
        if not target_acc:
            await interaction.followup.send("❌ Bạn chưa được Admin cấp tài khoản mặc định.", ephemeral=True)
            return

        result = await asyncio.wait_for(
            asyncio.to_thread(do_action_check, target_acc, True),
            timeout=90.0
        )

        if result is None:
            return

        if await _send_check_attachment(interaction, result, f"row_{target_acc}.png", target_acc):
            return

    except asyncio.TimeoutError:
        await interaction.followup.send("⏱️ Timeout!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Lỗi: {str(e)[:100]}", ephemeral=True)


@bot.tree.command(name="check_admin", description="[ADMIN] Kiểm tra trạng thái bất kỳ tài khoản nào")
@app_commands.describe(acc_name="Nhập số tài khoản hoặc tên tài khoản cần kiểm tra")
@admin_only
@control_required
async def cmd_check_admin(interaction: discord.Interaction, acc_name: str):
    await interaction.response.defer(ephemeral=True)
    try:
        if not get_game_window():
            await interaction.followup.send("❌ Game chưa khởi động!", ephemeral=True)
            return

        focus_game_window()

        target_acc = normalize_account_name(acc_name)
        if not target_acc:
            await interaction.followup.send("❌ Tên tài khoản không hợp lệ!", ephemeral=True)
            return

        result = await asyncio.wait_for(
            asyncio.to_thread(do_action_check, target_acc, True),
            timeout=90.0
        )

        if result is None:
            return

        if await _send_check_attachment(interaction, result, f"row_{target_acc}.png", target_acc):
            return

    except asyncio.TimeoutError:
        await interaction.followup.send("⏱️ Timeout!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Lỗi: {str(e)[:100]}", ephemeral=True)


@cmd_check_admin.error
async def cmd_check_admin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Bạn không có quyền **Administrator** để sử dụng lệnh này!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Bạn không có quyền **Administrator** để sử dụng lệnh này!", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Đã xảy ra lỗi khi thực thi lệnh.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Đã xảy ra lỗi khi thực thi lệnh.", ephemeral=True)


def start_bot():
    bot.run(BOT_TOKEN)
