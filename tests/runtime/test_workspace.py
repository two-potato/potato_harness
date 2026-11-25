"""Task-bound workspace preparation using actual local Git and SQLite."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from harness.controller import Controller, Event, ROOT, initialize
from harness.runtime.workspace import prepare_task_workspace, prepare_workspace, repository_identity


def git(repo,*args):
    return subprocess.check_output(['/usr/bin/git','-C',str(repo),*args]).decode().strip()


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.repo=self.root/'source'
        self.repo.mkdir()
        git(self.repo,'init')
        (self.repo/'api.py').write_bytes(b'value = 1\n')
        (self.repo/'ui.py').write_bytes(b'value = 2\n')
        (self.repo/'ui.py').chmod(0o755)
        (self.repo/'.gitattributes').write_text('api.py export-ignore\nui.py text eol=crlf\n')
        git(self.repo,'add','.')
        git(self.repo,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
        self.base=git(self.repo,'rev-parse','HEAD')
        self.store=self.root/'workspaces'
        self.store.mkdir(mode=0o700)
        self.db=self.root/'state.db'
        initialize(self.db)
        self.controller=Controller(self.db,guard=lambda c:c.after['status'] in ('CLASSIFIED','PLANNED'))

    def add(self,task_id,owner,scope,**extra):
        task=json.loads((ROOT/'fixtures/valid/task.json').read_text())
        commit={'hash_algorithm':'sha1','value':self.base}
        task.update(task_id=task_id,owner=owner,scope=scope,revision=0,row_version=0,
                    repository_id=repository_identity(self.repo),base_commit=commit,target_commit=commit)
        task.update(extra)
        task=self.controller.create_task(task,event_id=task_id,idempotency_key=task_id)
        for status in ('CLASSIFIED','PLANNED'):
            task=self.controller.transition(task_id,task['row_version'],Event(task_id+status,task_id+status,status))
        return task

    def test_two_task_workspaces_are_distinct_raw_git_copies(self):
        self.add('api','backend',['api.py'])
        self.add('ui','frontend',['ui.py'])
        a=prepare_task_workspace(self.db,self.store,self.repo,'api',0)
        b=prepare_task_workspace(self.db,self.store,self.repo,'ui',0)
        self.assertNotEqual(a['workspace_id'],b['workspace_id'])
        for result in (a,b):
            workspace=Path(result['workspace'])
            integration=Path(result['integration_repo'])
            self.assertFalse((workspace/'.git').exists())
            self.assertTrue((integration/'.git').is_dir())
            self.assertEqual(git(integration,'rev-parse','HEAD'),self.base)
            for name in ('api.py','ui.py','.gitattributes'):
                expected=subprocess.check_output(['/usr/bin/git','-C',str(self.repo),'show',self.base+':'+name])
                self.assertEqual((workspace/name).read_bytes(),expected)
                self.assertEqual((integration/name).read_bytes(),expected)
                self.assertEqual((workspace/name).stat().st_nlink,1)
            self.assertTrue((workspace/'ui.py').stat().st_mode & 0o111)
            self.assertEqual(json.loads((workspace.parent/'binding.json').read_text()),result)
        (Path(a['workspace'])/'api.py').write_text('changed\n')
        self.assertEqual((Path(b['workspace'])/'api.py').read_bytes(),b'value = 1\n')
        self.assertEqual((self.repo/'api.py').read_bytes(),b'value = 1\n')
        self.assertEqual((Path(a['integration_repo'])/'api.py').read_bytes(),b'value = 1\n')
        self.assertEqual(git(self.repo,'status','--porcelain'),'')
        self.assertEqual(self.controller.get_task('api')['status'],'PLANNED')

    def test_stale_foreign_or_duplicate_task_binding_rejected(self):
        self.add('api','backend',['api.py'])
        self.add('foreign','frontend',['ui.py'],repository_id='other')
        for task_id,revision in (('api',1),('api',False),('foreign',0)):
            with self.assertRaises(ValueError):
                prepare_task_workspace(self.db,self.store,self.repo,task_id,revision)
        self.assertEqual(list(self.store.iterdir()),[])
        a=prepare_task_workspace(self.db,self.store,self.repo,'api',0)
        with self.assertRaises(ValueError):
            prepare_task_workspace(self.db,self.store,self.repo,'api',0)
        self.assertTrue(Path(a['workspace']).is_dir())

    def test_dirty_repository_and_missing_scope_fail_closed(self):
        self.add('api','backend',['api.py'])
        self.add('missing','frontend',['missing.py'])
        (self.repo/'api.py').write_text('dirty\n')
        with self.assertRaises(ValueError):
            prepare_task_workspace(self.db,self.store,self.repo,'api',0)
        self.assertEqual(list(self.store.iterdir()),[])
        git(self.repo,'checkout','--','api.py')
        with self.assertRaises(ValueError):
            prepare_task_workspace(self.db,self.store,self.repo,'missing',0)
        self.assertFalse(any(self.store.glob('*/binding.json')))

    def test_workspace_root_cannot_alias_or_contain_source(self):
        self.add('api','backend',['api.py'])
        alias=self.root/'alias'
        alias.symlink_to(self.store,target_is_directory=True)
        broad=self.root/'broad'
        broad.mkdir(mode=0o755)
        inside=self.repo/'private'
        inside.mkdir(mode=0o700)
        for path in (alias,broad,inside):
            with self.assertRaises(ValueError):
                prepare_task_workspace(self.db,path,self.repo,'api',0)
        self.assertEqual(list(self.store.iterdir()),[])

    def test_tracked_symlink_fails_without_prepared_binding(self):
        (self.repo/'linked').symlink_to('api.py')
        git(self.repo,'add','linked')
        git(self.repo,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','alias')
        self.base=git(self.repo,'rev-parse','HEAD')
        self.add('api','backend',['api.py'])
        with self.assertRaises(ValueError):
            prepare_task_workspace(self.db,self.store,self.repo,'api',0)
        self.assertFalse(any(self.store.glob('*/binding.json')))

    def test_raw_layout_rejects_nonempty_root_and_unpinned_base(self):
        layout=self.root/'layout'
        layout.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            prepare_workspace(self.repo,'a'*40,['api.py'],layout)
        (layout/'existing').write_text('retain')
        with self.assertRaises(ValueError):
            prepare_workspace(self.repo,self.base,['api.py'],layout)
        self.assertEqual((layout/'existing').read_text(),'retain')
