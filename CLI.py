"""
Defines the command-line interface to McEnv
This is basically empty right now, since I can't forsee using this...
but who knows maybe we'll find a use for it.
"""

import sys, os, argparse, runpy, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def set_script_module(name, spec, var_dict):
    """
    Makes sure the script module is registered
    to break pickling issues if a __name__ == '__main__' block
    equivalent is called in the script
    """
    # multiprocessing fucks us over in a script environment
    # so we gotta do a bit of extra shit
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    for k,v in var_dict.items():
        setattr(mod, k, v)

class CLI:

    command_prefix='cli_method_'
    command_groups=['files']
    __env__ = ""

    def __init__(self, group=None, command=None):
        if group is None or command is None:
            self.argv = sys.argv
            parser = argparse.ArgumentParser()
            parser.add_argument("group", type=str)
            parser.add_argument("command", type=str, default='', nargs="?")
            parse, unknown = parser.parse_known_args()
            self.group = parse.group
            self.cmd = parse.command
            sys.argv = [sys.argv[0]] + unknown
        else:
            self.group = group
            self.cmd = command

    @staticmethod
    def get_parse_dict(*spec):
        argv_0 = sys.argv[0]
        try:
            sys.argv[0] = "parsing_dict" #self.group + " " + self.cmd
            parser = argparse.ArgumentParser()
            keys = []
            for arg in spec:
                if len(arg) > 1:
                    arg_name, arg_dict = arg
                else:
                    arg_name = arg[0]
                    arg_dict = {}
                if 'dest' in arg_dict:
                    keys.append(arg_dict['dest'])
                else:
                    keys.append(arg_name)
                parser.add_argument(arg_name, **arg_dict)
            args = parser.parse_args()
            opts = {k: getattr(args, k) for k in keys}
        finally:
            sys.argv[0] = argv_0
        return {k:o for k,o in opts.items() if not (isinstance(o, str) and o=="")}

    def get_command(self, group=None, cmd=None):
        if group is None:
            group = self.group
        if cmd is None:
            cmd = self.cmd
        try:
            fun = getattr(self, self.command_prefix + group + "_" + cmd.replace("-", "_"))
        except AttributeError:
            fun = "Unknown command '{}' for command group '{}'".format(cmd.replace("_", "-"), group)
        return fun

    def get_help(self):
        from collections import OrderedDict

        if self.group == "":
            groups = OrderedDict((k, OrderedDict()) for k in self.command_groups)
        else:
            groups = OrderedDict([(self.group, OrderedDict())])

        indent="    "
        template = "{group}:\n{commands}"
        if self.cmd == "":
            for k in vars(type(self)):
                for g in groups:
                    if k.startswith("cli_method_"+g):
                        groups[g][k.split("_", 1)[1].replace("_", "-")] = getattr(self, k)
        else:
            template = "{group}{commands}"
            indent = "  "
            groups[self.group][self.cmd] = self.get_command()

        blocks = []
        make_command_info = lambda name, fun, indent: "{0}{1}{3}{0}  {2}".format(
            indent,
            name,
            "" if fun.__doc__ is None else fun.__doc__.strip(),
            "\n" if fun.__doc__ is not None else ""
            )
        for g in groups:
            blocks.append(
                template.format(
                    group = g,
                    commands = "\n".join(make_command_info(k, f, indent) for k, f in groups[g].items())
                )
            )
        return "\n\n".join(blocks)

    def run(self):
        res = self.get_command()
        if not isinstance(res, str):
            res = res()
        else:
            print(res)
        return res

    def help(self, print_help=True):
        sys.argv.pop(1)
        res = self.get_help()
        if print_help:
            print(res)
        return res

    def __getstate__(self):
        """ Do nothing """
        return {}
    def __setstate__(self):
        """ Do nothing """
        pass
    @classmethod
    def run_command(cls, parse):
        # detect whether interactive run or not
        interact = parse.interact or (len(sys.argv) == 1 and not parse.help and not parse.script)

        # in interactive/script envs we expose stuff
        if parse.script or interact:
             sys.path.insert(0, os.getcwd())
             interactive_env = {
                 "__env__": "__script__"
                }
        # in a script environment we just read in the script and run it
        if parse.script:
            script = sys.argv[1]
            sys.argv.pop(0)
            if not os.path.exists(script):
                script_dir = os.path.join("/", "home", 'scripts')
                script = os.path.join(script_dir, script)
            sys.path.insert(0, os.path.dirname(script))
            script_mod=os.path.splitext(os.path.basename(script))[0]
            # importlib.import_module(script_mod)
            interactive_env["__name__"] = os.path.splitext(os.path.basename(script))[0]
            runpy.run_module(script_mod, init_globals={"__env__":"__script__"})
            # with open(script) as scr:
            #     src = scr.read()
            #     src = compile(src, script, 'exec')
            # interactive_env["__file__"] = script
            # exec(src, interactive_env, interactive_env)
        elif parse.help:
            if len(sys.argv) == 1:
                print("mcenv [--interact|--script] GRP CMD [ARGS] runs something in McEnv with the specified command")
            group = sys.argv[1] if len(sys.argv) > 1 else ""
            command = sys.argv[2] if len(sys.argv) > 2 else ""
            CLI(group=group, command=command).help()
        elif len(sys.argv) > 1:
            CLI().run()
        if interact:
            import code
            code.interact(banner="McEnv Interactive Session", readfunc=None, local=interactive_env, exitmsg=None)

    @classmethod
    def run_parse(cls, parse, unknown):
        sys.argv = [sys.argv[0]] + unknown
        # print(sys.argv)
        cls.run_command(parse)

    @classmethod
    def parse_and_run(cls):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--interact", default=False, action='store_const', const=True, dest="interact",
                            help='start an interactive session after running'
                            )
        parser.add_argument("--script", default=False, action='store_const', const=True, dest="script",
                            help='run a script'
                            )
        parser.add_argument("--help", default=False, action='store_const', const=True, dest="help")
        parser.add_argument("--fulltb", default=False, action='store_const', const=True, dest="full_traceback")
        new_argv = []
        for k in sys.argv[1:]:
            if not k.startswith("--"):
                break
            new_argv.append(k)
        unknown = sys.argv[1+len(new_argv):]
        sys.argv = [sys.argv[0]]+new_argv
        parse = parser.parse_args()

        if parse.full_traceback:
            cls.run_parse(parse, unknown)
        else:
            error = None
            try:
                cls.run_parse(parse, unknown)
            except Exception as e:
                error = e
            if error is not None:
                print(error)

if __name__ == "__main__":
    CLI.parse_and_run()