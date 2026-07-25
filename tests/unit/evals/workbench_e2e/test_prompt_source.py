import sqlite3

from evals.workbench_e2e.prompt_source import PromptSource


def test_prompt_source_loads_latest_version_and_binds_problem(tmp_path):
    database = tmp_path / "database.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        create table prompts(id integer primary key, name text, voice text);
        create table prompt_versions(
          id integer primary key, prompt_id integer,
          version_number integer, content text
        );
        insert into prompts values(98, 'geometry', null);
        insert into prompt_versions values(1, 98, 1, 'old {{problem}} __VOICE__');
        insert into prompt_versions values(2, 98, 2, 'new {{problem}} __VOICE__');
        """
    )
    connection.commit()
    connection.close()

    source = PromptSource(database)
    prompt = source.render(98, problem="P", solution="S")

    assert prompt.name == "geometry"
    assert prompt.version == 2
    assert "new P\n\n【解题过程】\nS" in prompt.text
    assert "__VOICE__" not in prompt.text
    assert prompt.text.endswith("# === END === 作为结束标记")
