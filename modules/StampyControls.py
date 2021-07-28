import sys
import discord
from modules.module import Module, Response
from config import rob_id, stampy_control_channel_names, TEST_RESPONSE_PREFIX
from utilities import get_github_info, get_memory_usage, get_running_user_info, get_question_id


class StampyControls(Module):
    """Module to manage stampy controls like reboot and resetinviteroles"""

    BOT_TEST_MESSAGE = "I'm alive!"
    RESET_INVITES_MESSAGE = "[resetting can-invite roles, please wait]"
    REBOOT_MESSAGE = "Rebooting..."
    REBOOT_DENIED_MESSAGE = "You're not my supervisor!"

    def __init__(self):
        super().__init__()
        self.routines = {
            "reboot": self.reboot,
            "resetinviteroles": self.resetinviteroles,
            "stats": self.get_stampy_stats,
        }

    def is_at_module(self, message):
        text = self.is_at_me(message)
        if text:
            return text.lower() in self.routines
        return False

    async def send_control_message(self, message, text):
        if self.utils.test_mode:
            question_id = get_question_id(message)
            await message.channel.send(TEST_RESPONSE_PREFIX + str(question_id) + ": " + text)
        else:
            await message.channel.send(text)

    def process_message(self, message, client=None):
        if self.is_at_module(message):
            routine_name = self.is_at_me(message).lower()
            routine = self.routines[routine_name]
            return Response(
                confidence=10,
                callback=routine,
                why="%s said '%s', which is a special command, so I ran the %s routine"
                % (message.author.name, routine_name, routine_name),
                args=[message],
            )
        return Response()

    @staticmethod
    async def reboot(message):
        if hasattr(message.channel, "name") and message.channel.name in stampy_control_channel_names:
            if message.author.id == rob_id:
                await message.channel.send("Rebooting...")
                sys.stdout.flush()
                exit()
        return Response(
            confidence=10,
            why="%s tried to kill me! They said 'reboot'" % message.author.name,
            text="You're not my supervisor!",
        )

    async def resetinviteroles(self, message):
        if self.utils.test_mode:
            print("Stampy is in test mode, not updating invite roles")
            return Response(
                confidence=10,
                why="%s asked me to reset roles, which" % message.author.name,
                text=self.RESET_INVITES_MESSAGE,
            )
        print("[resetting can-invite roles]")
        await self.send_control_message(message, self.RESET_INVITES_MESSAGE)
        guild = discord.utils.find(lambda g: g.name == self.utils.GUILD, self.utils.client.guilds)
        print(self.utils.GUILD, guild)
        role = discord.utils.get(guild.roles, name="can-invite")
        print("there are", len(guild.members), "members")
        reset_users_count = 0
        if not self.utils.test_mode:
            for member in guild.members:
                if self.utils.get_user_score(member) > 0:
                    print(member.name, "can invite")
                    await member.add_roles(role)
                    reset_users_count += 1
                else:
                    print(member.name, "has 0 stamps, can't invite")
        return Response(
            confidence=10,
            why="%s asked me to reset roles, which" % message.author.name,
            text="[Invite Roles Reset for %s users]" % reset_users_count,
        )

    def create_stampy_stats_message(self):
        git_message = get_github_info()
        run_message = get_running_user_info()
        memory_message = get_memory_usage()
        runtime_message = self.utils.get_time_running()
        modules_message = self.utils.list_modules()
        # scores_message = self.utils.modules_dict["StampsModule"].get_user_scores()
        return "\n\n".join([git_message, run_message, memory_message, runtime_message, modules_message])

    async def get_stampy_stats(self, message):
        """
        TODO: Make this its own module and add number of factoids
        """
        stats_message = self.create_stampy_stats_message()
        return Response(
            confidence=10, why="because %s asked for my stats" % message.author.name, text=stats_message
        )

    @property
    def test_cases(self):
        return [
            self.create_integration_test(question="reboot", expected_response=self.REBOOT_DENIED_MESSAGE),
            self.create_integration_test(
                question="resetinviteroles", expected_response=self.RESET_INVITES_MESSAGE
            ),
            self.create_integration_test(
                question="stats",
                expected_response=self.create_stampy_stats_message(),
                test_wait_time=4,
                minimum_allowed_similarity=0.8,
            ),
        ]

    def __str__(self):
        return "Stampy Controls Module"
