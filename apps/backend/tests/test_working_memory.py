from __future__ import annotations

import uuid

from jarvis_backend.ai import ChatMessage, ChatRole
from jarvis_backend.memory.working_memory import WorkingMemory


def test_append_and_get_round_trip() -> None:
    memory = WorkingMemory()
    conversation_id = uuid.uuid4()
    message = ChatMessage(role=ChatRole.USER, content="hello")

    memory.append(conversation_id, message)

    assert memory.get(conversation_id) == [message]


def test_get_returns_empty_list_for_unknown_conversation() -> None:
    memory = WorkingMemory()
    assert memory.get(uuid.uuid4()) == []


def test_conversations_are_isolated() -> None:
    memory = WorkingMemory()
    first_id, second_id = uuid.uuid4(), uuid.uuid4()

    memory.append(first_id, ChatMessage(role=ChatRole.USER, content="for first"))
    memory.append(second_id, ChatMessage(role=ChatRole.USER, content="for second"))

    assert memory.get(first_id)[0].content == "for first"
    assert memory.get(second_id)[0].content == "for second"


def test_buffer_respects_max_messages_bound() -> None:
    memory = WorkingMemory(max_messages_per_conversation=3)
    conversation_id = uuid.uuid4()

    for i in range(5):
        memory.append(conversation_id, ChatMessage(role=ChatRole.USER, content=f"msg {i}"))

    kept = memory.get(conversation_id)
    assert len(kept) == 3
    assert [m.content for m in kept] == ["msg 2", "msg 3", "msg 4"]


def test_clear_removes_conversation() -> None:
    memory = WorkingMemory()
    conversation_id = uuid.uuid4()
    memory.append(conversation_id, ChatMessage(role=ChatRole.USER, content="hi"))

    memory.clear(conversation_id)

    assert memory.get(conversation_id) == []
