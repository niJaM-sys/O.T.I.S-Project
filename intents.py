import ast
import datetime
import operator


class IntentRouter:
    def __init__(self, system_actions, spotify_controller):
        self.system_actions = system_actions
        self.spotify = spotify_controller

    def process(self, user_text, fallback_response_callback):
        direct_response = self.handle_direct_intent(user_text)
        if direct_response is not None:
            return direct_response

        return fallback_response_callback(user_text)

    def handle_direct_intent(self, user_text):
        normalized = self.normalize_text(user_text)
        if not normalized:
            return "I did not catch that, sir."

        spotify_result = self.spotify.handle_command(
            normalized,
            self.system_actions.open_application,
        )
        if spotify_result is not None:
            return spotify_result

        open_result = self.system_actions.handle_open_command(normalized)
        if open_result is not None:
            return open_result

        if self.is_date_question(normalized):
            return self.get_date_response()

        if self.is_time_question(normalized):
            return self.get_time_response()

        if self.is_weather_question(normalized):
            return (
                "I do not have a weather module yet, sir. "
                "For now, please check a reliable weather app or website."
            )

        math_expression = self.extract_math_expression(normalized)
        if math_expression is not None:
            result = self.safe_eval_math_expression(math_expression)
            if result is not None:
                if isinstance(result, float) and result.is_integer():
                    result = int(result)
                return str(result)

        return None

    def normalize_text(self, text):
        cleaned = (text or "").strip().lower()
        cleaned = cleaned.replace("’", "'")
        cleaned = cleaned.replace("'", " ")
        for char in [",", ".", "!", "?", ";", ":"]:
            cleaned = cleaned.replace(char, " ")
        cleaned = " ".join(cleaned.split())
        return cleaned

    def is_date_question(self, text):
        patterns = [
            "what day is it",
            "what s the date",
            "what is the date",
            "today s date",
            "what day are we",
            "what day are we today",
            "what day is today",
            "tell me the date",
        ]
        return any(pattern in text for pattern in patterns)

    def is_time_question(self, text):
        patterns = [
            "what time is it",
            "what s the time",
            "what is the time",
            "current time",
            "time now",
            "tell me the time",
        ]
        return any(pattern in text for pattern in patterns)

    def is_weather_question(self, text):
        keywords = [
            "weather",
            "temperature",
            "forecast",
            "is it raining",
            "is it sunny",
            "is it cold",
            "is it hot",
        ]
        return any(keyword in text for keyword in keywords)

    def get_date_response(self):
        now = datetime.datetime.now()
        return now.strftime("Today is %A, %B %d, %Y, sir.")

    def get_time_response(self):
        now = datetime.datetime.now()
        return now.strftime("It is %H:%M, sir.")

    def extract_math_expression(self, text):
        if not any(char.isdigit() for char in text):
            return None

        expression = text

        replacements = {
            "what is": "",
            "what s": "",
            "calculate": "",
            "compute": "",
            "how much is": "",
            "plus": "+",
            "minus": "-",
            "multiplied by": "*",
            "times": "*",
            "x": "*",
            "divided by": "/",
            "over": "/",
        }

        for old, new in replacements.items():
            expression = expression.replace(old, new)

        filtered = []
        for char in expression:
            if char.isdigit() or char in "+-*/(). ":
                filtered.append(char)
            else:
                filtered.append(" ")

        expression = "".join(filtered)
        expression = " ".join(expression.split())

        if not expression:
            return None

        if not any(op in expression for op in "+-*/"):
            return None

        return expression

    def safe_eval_math_expression(self, expression):
        allowed_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.USub: operator.neg,
        }

        def evaluate_node(node):
            if isinstance(node, ast.Expression):
                return evaluate_node(node.body)

            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)):
                    return node.value
                raise ValueError("Invalid constant")

            if isinstance(node, ast.Num):
                return node.n

            if isinstance(node, ast.BinOp):
                if type(node.op) not in allowed_operators:
                    raise ValueError("Operator not allowed")
                left = evaluate_node(node.left)
                right = evaluate_node(node.right)
                return allowed_operators[type(node.op)](left, right)

            if isinstance(node, ast.UnaryOp):
                if type(node.op) not in allowed_operators:
                    raise ValueError("Unary operator not allowed")
                operand = evaluate_node(node.operand)
                return allowed_operators[type(node.op)](operand)

            raise ValueError("Unsupported expression")

        try:
            parsed = ast.parse(expression, mode="eval")
            return evaluate_node(parsed)
        except Exception:
            return None
