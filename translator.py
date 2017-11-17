# -*- coding: utf-8 -*-
"""Translator and Python code generator module for event2py

Translates HHS+ events to Python code.

Copyright (C) 2017 Radomir Matveev GPL 3.0+

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

# --------------------------------------------------------------------------- #
# Import libraries
# --------------------------------------------------------------------------- #
import logging
from collections import OrderedDict
from pathlib import Path
from lxml import etree


# --------------------------------------------------------------------------- #
# Define classes
# --------------------------------------------------------------------------- #
class XmlModel(object):
    """The base class for all XML models."""

    @staticmethod
    def _from_xml(obj, xmlelem):
        for childelem in xmlelem:
            obj.parse_child(childelem)
        return obj

    @classmethod
    def from_xml(cls, xmlelem):
        obj = cls()
        return XmlModel._from_xml(obj, xmlelem)

    def __init__(self):
        pass

    def parse_attribute(self, xmlelem, tagmap=None):
        if tagmap is None:
            tagmap = {}
        attr = tagmap.get(xmlelem.tag,
                          capitalized_to_underscores(xmlelem.tag))
        if not hasattr(self, attr):
            log.info("Ignoring XML element %s", xmlelem)
            return
        setattr(self, attr, cast_text(xmlelem))


class VESeqObjectsModel(XmlModel):
    def __init__(self):
        super().__init__()
        self.idmap = {}

    def get_action(self, actid, default=None):
        return self.idmap.get(actid, default)

    def parse_child(self, xmlelem):
        tag = xmlelem.tag
        log.info("Parse action %s", tag)
        # for now we treat conditions and delayed(?) actions
        # as simple actions
        tag = tag.replace("SeqAct_", "")
        tag = tag.replace("SeqActLat_", "")
        tag = tag.replace("SeqCond_", "")
        # the SeqEvent is the start action
        tag = tag.replace("SeqEvent", "Start")
        clsname = tag + "Action"
        ActionCls = globals().get(clsname, VisualEventAction)
        if ActionCls is VisualEventAction:
            log.warning("No model for action %s", tag)
        act = ActionCls.from_xml(xmlelem)
        assert act.actid not in self.idmap
        self.idmap[act.actid] = act


# TODO: implement randomization, e.g.
#   <MinRandom>4</MinRandom>
#   <IsRandom>true</IsRandom>
class VESeqVarsModel(XmlModel):
    def __init__(self):
        super().__init__()
        self.idmap = {}

    def get_var(self, varid, default=None):
        return self.idmap.get(varid, default)

    def update_var(self, varid, key, value):
        self.idmap[varid][key] = value

    def parse_child(self, xmlelem):
        varid = cast_text(xmlelem.find("ID"))
        vartype = xmlelem.tag.replace("SeqVar_", "")
        varmap = {"type": vartype}
        if vartype == "ObjectList":
            data = []
        else:
            tagmap = {"String": "Str",
                      "Double": "Dbl"}
            datatag = tagmap.get(vartype, vartype)
            data = cast_child_text(xmlelem, datatag, "nodata")
        if data == "nodata":
            if vartype not in {"Int"}:
                log.warning("Could not parse content of %s variable %s",
                            vartype, varid)
            varmap["content"] = None
        else:
            varmap["content"] = data
        assert varid not in self.idmap
        self.idmap[varid] = varmap


class VisualEventAction(XmlModel):

    @staticmethod
    def _from_xml(obj, xmlelem):
        for childelem in xmlelem:
            obj.parse_child(childelem)
        return obj

    def __init__(self):
        super().__init__()
        self.actid = None
        self.comment = None
        self.input_links = OrderedDict()
        self.output_links = OrderedDict()
        self.variable_links = OrderedDict()

    def parse_child(self, xmlelem):
        if xmlelem.tag == "OutputLinks":
            for linkelem in xmlelem:
                self.parse_output_link(linkelem)
        elif xmlelem.tag == "VariableLinks":
            for linkelem in xmlelem:
                self.parse_variable_link(linkelem)
        else:
            tagmap = {"ID": "actid"}
            self.parse_attribute(xmlelem, tagmap)

    def parse_output_link(self, xmlelem):
        linkmap = cast_link(xmlelem)
        linkname = linkmap.pop("name")
        if linkname is None:
            log.warning("Ignoring output link '%s', no name specified",
                        linkmap["name"])
            return
        assert linkname not in self.output_links, self.output_links
        self.output_links[linkname] = linkmap

    def parse_variable_link(self, xmlelem):
        varmap = cast_variable_link(xmlelem)
        varname = varmap.pop("name")
        if varname is None:
            log.warning("Ignoring variable link '%s', no name specified",
                        varmap["name"])
            return
        assert varname not in self.variable_links
        self.variable_links[varname] = varmap

    def to_lines(self, actions, variables):
        log.info("Translate action %s", self.__class__.__name__)
        lines = ScriptLines()
        if self.comment is None:
            lines.append('# action %s' % self.actid)
        else:
            lines.append('# action %s: %s' % (self.actid, self.comment))
        return lines

    def outlinks_to_lines(self, actions, variables):
        lines = ScriptLines()
        for outlink in self.output_links.values():
            if outlink["id"] is None:
                continue
            act = actions.get_action(outlink["id"])
            lines.extend(act.to_lines(actions, variables))
        return lines

    def outlink_to_lines(self, actions, variables, name):
        lines = ScriptLines()
        outlink = self.get_out_link(name)
        if outlink["id"] is None:
            lines.append("return")
        else:
            act = actions.get_action(outlink["id"])
            lines.extend(act.to_lines(actions, variables))
        return lines

    def get_var_link(self, name, default=None):
        try:
            return self.variable_links[name]
        except KeyError as keyerr:
            if default is None:
                valerr = ValueError("No variable link named '%s' in %s"
                                    % (name, self))
                raise valerr from keyerr
            return default

    def get_out_link(self, name, default=None):
        try:
            return self.output_links[name]
        except KeyError as keyerr:
            if default is None:
                valerr = ValueError("No output link named '%s' in %s"
                                    % (name, self))
                raise valerr from keyerr
            return default


class StartAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables, data):
        lines = super().to_lines(actions, variables)
        lines.insert(0, '# import game interface', 0)
        lines.insert(1, 'from events import GameInterface', 0)
        lines.insert(2, '', 0)
        lines.insert(3, '', 0)
        lines.append('def try_():')
        lines.extend(self.outlink_to_lines(actions, variables, "Try"))
        lines.close_function()

        lines.append('def execute():')
        lines.extend(self.outlink_to_lines(actions, variables, "Execute"))
        lines.close_function()
        lines.append('# define variables')
        lines.append('game = GameInterface()')
        lines.append('eventname = "%s"' % data["eventname"])
        lines.append('')
        return lines


class TODOAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        var = variables.get_var(self.get_var_link("Message")["id"])
        lines.append('print("""%s""")' % var["content"])
        return lines


class GetPersonListAction(VisualEventAction):

    def __init__(self):
        super().__init__()
        self.list_kind = None

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        varlink = self.get_var_link("List")
        varid = varlink["id"]
        varname = 'person_list_%s' % varid
        variables.update_var(varid, "pyname", varname)
        lines.append('%s = game.get_person_list("%s")'
                     % (varname, self.list_kind))
        lines.extend(self.outlinks_to_lines(actions, variables))
        return lines


class GetListCountAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        varlink = self.get_var_link("List")
        varid = varlink["id"]
        invar = variables.get_var(varid)
        inname = invar["pyname"]
        outname = 'len_%s' % inname
        varlink = self.get_var_link("Count")
        varid = varlink["id"]
        variables.update_var(varid, "pyname", outname)
        comment = '  # var id %s' % varid
        lines.append('{outname} = len({inname}){comment}'.format_map(locals()))
        lines.extend(self.outlinks_to_lines(actions, variables))
        return lines


class AcceptEventAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        lines.append('return True  # accept event')
        return lines


class ClearObjectListAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        varlink = self.get_var_link("List")
        var = variables.get_var(varlink["id"])
        lines.append('%s = []' % var["pyname"])
        lines.extend(self.outlinks_to_lines(actions, variables))
        return lines


class CompareIntSplitAction(VisualEventAction):

    def __init__(self):
        super().__init__()
        self.split_points = []

    def parse_child(self, xmlelem):
        if xmlelem.tag == "SplitPoints":
            self.split_points = cast_children_texts(xmlelem, ["int"])
        else:
            super().parse_child(xmlelem)

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        varlink = self.get_var_link("Var")
        var = variables.get_var(varlink["id"])
        vn = var["pyname"]
        splits = self.split_points[:]
        sp = splits.pop(0)
        lines.append('if {vn} < {sp}:'.format_map(locals()))
        linkname = "< %s" % sp
        lines.extend(self.outlink_to_lines(actions, variables, linkname))
        lines.indent_level -= 1
        while len(splits) > 0:
            sp = splits.pop(0)
            lines.append('elif {vn} < {sp}:'.format_map(locals()))
            linkname = "< %s" % sp
            lines.extend(self.outlink_to_lines(actions, variables, linkname))
            lines.indent_level -= 1
        lines.append('else:')
        linkname = ">= %s" % sp
        lines.extend(self.outlink_to_lines(actions, variables, linkname))
        lines.indent_level -= 1
        return lines


class IsScheduledForTodayAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        lines.append('if game.is_scheduled_for_today(eventname) is False:')
        lines.extend(self.outlink_to_lines(actions, variables, "False"))
        lines.indent_level -= 1
        lines.extend(self.outlink_to_lines(actions, variables, "True"))
        return lines


class CheckDaylightAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        lines.append('daylight_check = game.check_daylight()')
        for cond, daytime in zip(("if", "elif", "elif", "elif"),
                                 ("Day", "Night", "Sunrise", "Sunset")):
            l = '{cond} daylight_check == "{daytime}":'.format_map(locals())
            lines.append(l)
            lines.extend(self.outlink_to_lines(actions, variables, daytime))
            lines.indent_level -= 1
        return lines


class ShowRandomImageAction(VisualEventAction):

    def __init__(self):
        super().__init__()
        self.images = set()

    def parse_child(self, xmlelem):
        if xmlelem.tag == "Images":
            for imgelem in xmlelem.findall("FilteredImage"):
                imgpath = cast_child_text(imgelem, "ImagePath")
                self.images.add("/".join(Path(imgpath).parts))
        else:
            super().parse_child(xmlelem)

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        lines.append('import random')
        lines.append('')
        lines.append('images = {')
        images = self.images.copy()
        while len(images) > 1:
            lines.append('         "%s",' % images.pop())
        lines.append('         "%s"' % images.pop())
        lines.append('         }')
        lines.append('game.show_image(random.choice(images))')
        lines.append('')
        lines.extend(self.outlink_to_lines(actions, variables, "Out"))
        return lines


class ShowTextAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        varlink = self.get_var_link("Text")
        var = variables.get_var(varlink["id"])
        lines.append('game.show_text("""%s""")' % var["content"])
        lines.extend(self.outlink_to_lines(actions, variables, "Out"))
        return lines


class PassTimeAction(VisualEventAction):

    def __init__(self):
        super().__init__()
        self.time_pass_type = None

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        hours = variables.get_var(self.get_var_link("Hours")["id"], 0)
        minutes = variables.get_var(self.get_var_link("Minutes")["id"], 0)
        if hours is not 0:
            print("h", hours)
            hours = hours["content"]
        if minutes is not 0:
            print("min", minutes)
            minutes = minutes["content"]
        tptype = self.time_pass_type.lower()
        lines.append('game.pass_time(' +
                     '{hours}, {minutes}, "{tptype}")'.format_map(locals()))
        lines.extend(self.outlink_to_lines(actions, variables, "Out"))
        return lines


class RandomChanceAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        varid = self.get_var_link("Chance")["id"]
        var = variables.get_var(varid)
        assert var is not None
        lines.append('from random import randint')
        lines.append('')
        lines.append('if %s < randint(1, 100):  # not passed' % var["content"])
        lines.extend(self.outlink_to_lines(actions, variables, "Not Passed"))
        lines.indent_level -= 1
        lines.extend(self.outlink_to_lines(actions, variables, "Passed"))
        return lines


class MinObjListElementsAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        listvar = variables.get_var(self.get_var_link("List")["id"])
        minvar = variables.get_var(self.get_var_link("Min")["id"])
        lines.append('if len(%s) < %s:'
                     % (listvar["pyname"], minvar["content"]))
        lines.extend(self.outlink_to_lines(actions, variables, "<"))
        lines.indent_level -= 1
        lines.extend(self.outlink_to_lines(actions, variables, ">="))
        return lines


class ListFilterGenderAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        listvar = variables.get_var(self.get_var_link("List Source")["id"])
        listvar_pyname = listvar["pyname"]
        for varname in ("Males", "Females", "Futanaris"):
            var = variables.get_var(self.get_var_link(varname)["id"])
            if var is None:
                continue
            if "pyname" not in var:
                var["pyname"] = varname.lower() + "_" + listvar_pyname
            lines.append('%s = [p for p ' % var["pyname"] +
                         'in %s ' % listvar_pyname +
                         'if p.gender == "%s"]' % varname.lower()[:-1])
        lines.extend(self.outlink_to_lines(actions, variables, "Out"))
        return lines


class SetScheduleAction(VisualEventAction):

    def __init__(self):
        super().__init__()

    def to_lines(self, actions, variables):
        lines = super().to_lines(actions, variables)
        var = variables.get_var(self.get_var_link("Days")["id"])
        lines.append('game.set_schedule(eventname, days=%s)' % var["content"])
        return lines


class VisualEventModel(XmlModel):

    # TODO: consolidate with XmlModel.parse_attribute
    # maps XML tags to python attributes
    tagmap = {
            }

    @classmethod
    def from_path(cls, path):
        rootelem = load_xml_ressource(path)
        obj = cls.from_xml(rootelem)
        obj.file_path = path
        return obj

    def __init__(self):
        super().__init__()
        self.file_path = None
        self.trigger_type = None
        self.seq_objects = None
        self.seq_vars = None

    def parse_child(self, xmlelem):
        tag = xmlelem.tag.replace("_", "")
        defattr = capitalized_to_underscores(tag)  # default attribute name
        modelclassname = "VE%sModel" % tag
        modelcls = globals().get(modelclassname, None)
        if modelcls is None:
            if xmlelem.text is None:
                log.info("Ignoring XML element %s", xmlelem)
            else:
                val = cast_xml_type(xmlelem.text)
        else:
            val = modelcls.from_xml(xmlelem)
        attr = self.tagmap.get(tag, defattr)
        if hasattr(self, attr):
            setattr(self, attr, val)
        else:
            log.info("Ignoring XML element %s", xmlelem)

    def to_script(self):
        """Create an event script in Python from this model."""
        startact = self.seq_objects.get_action(0)
        startdata = {}
        if self.file_path is not None:
            startdata["eventname"] = self.file_path.name.replace(".ve.xml", "")
        lines = startact.to_lines(self.seq_objects, self.seq_vars, startdata)
        return lines


class ScriptLines(object):
    """Represents lines of a python script."""
    def __init__(self):
        self.lines = []
        self.indent_sep = "    "  # 4 spaces
        self.indent_level = 0

    def __str__(self):
        return "\n".join(self.lines)

    def __iter__(self):
        return iter(self.lines)

    @property
    def indent(self):
        return self.indent_sep * self.indent_level

    def append(self, line):
        line = line.rstrip()
        self.lines.append(self.indent + line)
        if "#" in line:
            line, comment = line.split("#", 1)
        if line.rstrip().endswith(":"):
            self.indent_level += 1

    def extend(self, lines):
        for line in lines:
            self.lines.append(self.indent + line.rstrip())

    def insert(self, idx, line, indent_level):
        """Inserts the line at the specified line index."""
        self.lines.insert(idx, self.indent_sep * indent_level + line.rstrip())

    def close_method(self):
        self.indent_level -= 1
        self.append('')

    def close_function(self):
        self.close_method()
        self.append('')
    close_class = close_function


# --------------------------------------------------------------------------- #
# Define functions
# --------------------------------------------------------------------------- #
def load_xml_ressource(filepath):
    """Returns the root of the XML tree in the file."""
    if isinstance(filepath, str):
        filepath = Path(filepath)
    tree = etree.parse(filepath.open("r", encoding="utf-8"))
    return tree.getroot()


def capitalized_to_underscores(text):
    """Converts capitalized words to words with underscores."""
    chars = [text[0].lower()]
    for c in text[1:]:
        if c.isupper():
            chars.append("_")
            chars.append(c.lower())
        else:
            chars.append(c)
    return "".join(chars)


def underscores_to_capitalized(text):
    """Converts words with underscores to capitalized words."""
    chars = [text[0].upper()]
    chariter = iter(text[1:])
    for c in chariter:
        if c == "_":
            chars.append(next(chariter).upper())
        else:
            chars.append(c)
    return "".join(chars)


def cast_xml_type(text):
    """Casts XML text to an appropriate python type."""
    # test for integers
    try:
        return int(text.strip())
    except ValueError:
        pass
    # test for floats
    try:
        return float(text.strip())
    except ValueError:
        pass
    # test for boolean
    if text == "true":
        return True
    if text == "false":
        return False
    # assume its just a string
    return text


def cast_text(xmlelem, default=None):
    """Parse the text of a XML element into a python type.

    If the given xml element has no text the default value is returned,
    unless no default value was specified, in which case ValueError is
    raised.
    """
    text = xmlelem.text
    if text is None:
        if default is None:
            raise ValueError("Element has no text: %s" % xmlelem)
        return default
    return cast_xml_type(text)


def cast_child_text(xmlelem, tag, default=None):
    """Parse the text of the child of an XML element into a python type.

    If a default value is specified it is returned if xmlelem has no child
    with this tag, or if that child has no text.
    If no default value is specified and xmlelem has no child with that tag or
    if the child has no text ValueError is raised.
    """
    child = xmlelem.find(tag)
    if child is None:
        if default is None:
            raise ValueError("No child with tag '%s' in %s" % (tag, xmlelem))
        return default
    return cast_text(child, default)


def cast_children_texts(xmlelem, tags=None):
    """Parse the texts of all children with one of the specified tags.

    If no tags are specified the texts of all children of the given XML
    element are parsed.
    """
    if tags is None:
        children = list(xmlelem)
    else:
        children = []
        for tag in tags:
            children.extend(xmlelem.findall(tag))
    return [cast_text(child) for child in children]


def cast_range(xmlelem):
    """Cast an integer range specified in XML to a tuple.

    The passed xml element must have the following structure:
            <any_tag>
                <Min>0</Min>
                <Max>50</Max>
            </any_tag>
    """
    minval = cast_xml_type(xmlelem.find("Min").text)
    maxval = cast_xml_type(xmlelem.find("Max").text)
    return (minval, maxval)


def cast_coords(xmlelem):
    """Cast coordinates specified in XML to a tuple.

    The passed xml element must have the following structure:
            <any_tag>
                <Coords>
                    <X>20</X>
                    <Y>4</Y>
                </Coords>
            </any_tag>
    """
    return cast_children_texts(xmlelem.find("Coords"), tags=("X", "Y"))


def cast_id(xmlelem, idlisttag):
    """Casts an id specified in XML to an int.

    The passed xml element must have the following structure:
            <any_tag>
                <idlisttag>
                    <unsignedInt>2</unsignedInt>
                </idlisttag>
            </any_tag>
    """
    idlistelem = xmlelem.find(idlisttag)
    if idlistelem is None:
        return
    idelem = idlistelem.find("unsignedInt")
    return cast_text(idelem)


def cast_link(xmlelem):
    linkmap = {
            "name": cast_text(xmlelem.find("Name")),
            "id": cast_id(xmlelem, "OutputIDs"),
            }
    return linkmap


def cast_variable_link(xmlelem):
    varmap = {
            "name": cast_text(xmlelem.find("Name")),
            "id": cast_id(xmlelem, "VariableIDs"),
            "expected_type": cast_child_text(xmlelem, "ExpectedType"),
            "read_only": cast_child_text(xmlelem, "bReadOnly", False),
            "write_only": cast_child_text(xmlelem, "bWriteOnly", False)
            }
    return varmap


# --------------------------------------------------------------------------- #
# Define module globals
# --------------------------------------------------------------------------- #
log = logging.getLogger(__name__)
