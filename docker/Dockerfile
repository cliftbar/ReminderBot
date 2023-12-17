FROM python:3.11-alpine

WORKDIR ReminderBot
ADD . .

RUN pip install -r requirements/requirements.txt

CMD cd src && python main.py
