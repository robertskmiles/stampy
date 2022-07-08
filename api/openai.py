from config import CONFUSED_RESPONSE, openai_channels, openai_api_key, rob_id
from modules.module import Module, Response
from transformers import GPT2TokenizerFast
from utilities.serviceutils import Services, ServiceMessage
import openai
import discord

openai.api_key = openai_api_key
start_sequence = "\nA:"
restart_sequence = "\n\nQ: "

default_italics_mark = "*"
slack_italics_mark = "_"


class OpenAI:
    def __init__(self):
        super().__init__()
        self.class_name = self.__class__.__name__
        self.allowed_channels: dict[Services, list[str]] = {}
        for channel, service in openai_channels:
            if service not in self.allowed_channels:
                self.allowed_channels[service] = [channel]
            else:
                self.allowed_channels[service].append(channel)

    def is_channel_allowed(self, message: ServiceMessage) -> bool:
        if message.service not in self.allowed_channels:
            return False
        return message.channel.name in self.allowed_channels[message.service]

    def get_forbidden_tokens(self, channel):
        """Go through the chatlog and find the tokens that start each of stampy's own messages
        This is so that we can tell GPT-3 not to use those tokens, to prevent repetition"""

        forbidden_tokens = set([])

        for message in self.message_logs[channel]:
            if message.author.name == "stampy":
                # we only need the first token, so just clip to ten chars
                # the space is because we generate from "stampy:" so there's always a space at the start
                text = " " + message.clean_content[:10].strip("*")
                forbidden_token = self.tokenizer(text)["input_ids"][0]
                forbidden_tokens.add(forbidden_token)
                self.log.info(self.class_name, text=text, forbidden_token=forbidden_token)

        return forbidden_tokens

    def cf_risk_level(self, prompt):
        """Ask the openai content filter if the prompt is risky
        Returns:
            0 - The text is safe.
            1 - This text is sensitive.
            2 - This text is unsafe.

        See https://beta.openai.com/docs/engines/content-filter for details"""

        try:
            response = openai.Completion.create(
                engine="content-filter-alpha",
                prompt="<|endoftext|>" + prompt + "\n--\nLabel:",
                temperature=0,
                max_tokens=1,
                top_p=0,
                logprobs=10,
            )
        except openai.error.AuthenticationError:
            self.log.error(self.class_name, error="OpenAI Authentication Failed")
            return 2
        except openai.error.RateLimitError:
            self.log.warning(self.class_name, error="OpenAI Rate Limit Exceeded")
            return 2

        output_label = response["choices"][0]["text"]

        # This is the probability at which we evaluate that a "2" is likely real
        # vs. should be discarded as a false positive
        toxic_threshold = -0.355

        if output_label == "2":
            # If the model returns "2", return its confidence in 2 or other output-labels
            logprobs = response["choices"][0]["logprobs"]["top_logprobs"][0]

            # If the model is not sufficiently confident in "2",
            # choose the most probable of "0" or "1"
            # Guaranteed to have a confidence for 2 since this was the selected token.
            if logprobs["2"] < toxic_threshold:
                logprob_0 = logprobs.get("0", None)
                logprob_1 = logprobs.get("1", None)

                # If both "0" and "1" have probabilities, set the output label
                # to whichever is most probable
                if logprob_0 is not None and logprob_1 is not None:
                    if logprob_0 >= logprob_1:
                        output_label = "0"
                    else:
                        output_label = "1"
                # If only one of them is found, set output label to that one
                elif logprob_0 is not None:
                    output_label = "0"
                elif logprob_1 is not None:
                    output_label = "1"

                # If neither "0" or "1" are available, stick with "2"
                # by leaving output_label unchanged.

        # if the most probable token is none of "0", "1", or "2"
        # this should be set as unsafe
        if output_label not in ["0", "1", "2"]:
            output_label = "2"

        self.log.info(self.class_name, msg=f"Prompt is risk level {output_label}")

        return int(output_label)

    def get_engine(self, message):
        """Pick the appropriate engine to respond to a message with"""

        guild, _ = self.get_guild_and_invite_role()

        bot_dev_role = discord.utils.get(guild.roles, name="bot dev")
        member = guild.get_member(message.author.id)

        if message.author.id == rob_id:
            return "text-davinci-001"
        elif member and (bot_dev_role in member.roles):
            return "text-curie-001"
        else:
            return "text-babbage-001"

    async def gpt3_chat(self, message):
        """Ask GPT-3 what Stampy would say next in the chat log"""

        engine = self.get_engine(message)
        prompt = self.generate_chatlog_prompt(message.channel)

        if self.cf_risk_level(prompt) > 1:
            return Response(
                confidence=0, text="", why=f"GPT-3's content filter thought the prompt was risky",
            )

        forbidden_tokens = self.get_forbidden_tokens(message.channel)
        self.log.info(self.class_name, forbidden_tokens=forbidden_tokens)
        logit_bias = {
            9: -100,  # "*"
            1174: -100,  # "**"
            8162: -100,  # "***"
            1635: -100,  # " *"
            12429: -100,  # " **"
            17202: -100,  # " ***"
        }
        for forbidden_token in forbidden_tokens:
            logit_bias[forbidden_token] = -100

        try:
            response = openai.Completion.create(
                engine=engine,
                prompt=prompt,
                temperature=0,
                max_tokens=100,
                top_p=1,
                # stop=["\n"],
                logit_bias=logit_bias,
                user=str(message.author.id),
            )
        except openai.error.AuthenticationError:
            self.log.error(self.class_name, error="OpenAI Authentication Failed")
            return Response()
        except openai.error.RateLimitError:
            self.log.warning(self.class_name, error="OpenAI Rate Limit Exceeded")
            return Response(why="Rate Limit Exceeded")

        if response["choices"]:
            choice = response["choices"][0]
            if choice["finish_reason"] == "stop" and choice["text"].strip() != "Unknown":
                text = choice["text"].strip(". \n").split("\n")[0]
                self.log.info(self.class_name, gpt_response=text)
                if message.service == Services.SLACK:
                    im = slack_italics_mark
                else:
                    im = default_italics_mark
                return Response(confidence=10, text=f"{im}{text}{im}", why="GPT-3 made me say it!",)

        return Response()

    async def gpt3_question(self, message):
        """Ask GPT-3 for an answer"""

        engine = self.get_engine(message)

        text = self.is_at_me(message)
        if text.endswith("?"):
            self.log.info(self.class_name, status="Asking GPT-3")
            prompt = self.start_prompt + text + start_sequence

            if self.cf_risk_level(prompt) > 1:
                return Response(
                    confidence=0, text="", why=f"GPT-3's content filter thought the prompt was risky",
                )

            try:
                response = openai.Completion.create(
                    engine=engine,
                    prompt=prompt,
                    temperature=0,
                    max_tokens=100,
                    top_p=1,
                    user=str(message.author.id),
                    # stop=["\n"],
                )
            except openai.error.AuthenticationError:
                self.log.error(self.class_name, error="OpenAI Authentication Failed")
                return Response()
            except openai.error.RateLimitError:
                self.log.warning(self.class_name, error="OpenAI Rate Limit Exceeded")
                return Response(why="Rate Limit Exceeded")

            if response["choices"]:
                choice = response["choices"][0]
                if choice["finish_reason"] == "stop" and choice["text"].strip() != "Unknown":
                    self.log.info(self.class_name, status="Asking GPT-3")
                    return Response(
                        confidence=10,
                        text="*" + choice["text"].strip(". \n") + "*",
                        why="GPT-3 made me say it!",
                    )

        # if we haven't returned yet
        self.log.error(self.class_name, error="GPT-3 didn't make me say anything")
        return Response()
