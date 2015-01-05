"""Provide the Query class.
"""

import icat.client
import icat.entity
import icat.entities
from icat.exception import InternalError

__all__ = ['Query']

substnames = {
    "datafileFormat":"dff",
    "dataset":"ds",
    "dataset.investigation":"i",
    "facility":"f",
    "grouping":"g",
    "instrumentScientists":"isc",
    "investigation":"i",
    "investigationGroups":"ig",
    "investigationInstruments":"ii",
    "investigationUsers":"iu",
    "parameters":"p",
    "parameters.type":"pt",
    "type":"t",
    "user":"u",
    "userGroups":"ug",
}
"""Symbolic names for the representation of related objects in
JOIN ... AS and INCLUDE ... AS.  Prescribing sensible names makes the
search expressions somewhat better readable.  There is no need for
completeness here.
"""

def getentityclassbyname(client, name):
    """Return the Entity class corresponding to a BeanName for the client.
    """
    # FIXME: consider to make this a client method.
    for c in client.typemap.values():
        if name == c.BeanName:
            return c
    else:
        raise ValueError("Invalid entity type '%s'." % name)

def getnaturalorder(client, entity):
    """Return the natural order of the Enitity class entity.
    """
    # FIXME: consider to make this a client method or a class method
    # in Entity.
    order = []
    attrs = list(entity.SortAttrs or entity.Constraint)
    if "id" in entity.Constraint and "id" not in attrs:
        attrs.append("id")
    for a in attrs:
        attrInfo = entity.getAttrInfo(client, a)
        if attrInfo.relType == "ATTRIBUTE":
            order.append(a)
        elif attrInfo.relType == "ONE":
            rclass = getentityclassbyname(client, attrInfo.type)
            rorder = getnaturalorder(client, rclass)
            order.extend(["%s.%s" % (a, ra) for ra in rorder])
        elif attrInfo.relType == "MANY":
            # skip, one to many relationships cannot be used in an
            # ORDER BY clause.
            continue
        else:
            assert False, "Invalid relType: '%s'" % attrInfo.relType
    return order

def parents(obj):
    """Iterate over the parents of obj as dot separated components.

    >>> list(parents("a.bb.c.ddd.e.ff"))
    ['a', 'a.bb', 'a.bb.c', 'a.bb.c.ddd', 'a.bb.c.ddd.e']
    >>> list(parents("abc"))
    []
    """
    s = 0
    while True:
        i = obj.find('.', s)
        if i < 0:
            break
        yield obj[:i]
        s = i+1

def makesubst(objs):
    subst = {}
    substcount = 0
    for obj in sorted(objs):
        for o in parents(obj):
            if o not in subst:
                if o in substnames and substnames[o] not in subst.values():
                    subst[o] = substnames[o]
                else:
                    substcount += 1
                    subst[o] = "s%d" % substcount
    return subst

def dosubst(obj, subst):
    i = obj.rfind('.')
    if i < 0:
        n = "o.%s" % (obj)
    else:
        n = "%s.%s" % (subst[obj[:i]], obj[i+1:])
    if obj in subst:
        n += " AS %s" % (subst[obj])
    return n

class Query(object):
    """Build a query to search an ICAT server.

    The query uses the JPQL inspired syntax introduced with ICAT
    4.3.0.  It won't work with older ICAT servers.
    """

    def __init__(self, client, entity, 
                 order=None, conditions=None, includes=None):

        """Initialize the query.

        :param client: the ICAT client.
        :type client: `Client`
        :param entity: the type of objects to search for.  This may
            either be an ``Entity`` subclass or the name of an entity
            type.
        :type entity: `Entity` or ``str``
        :param order: the sorting attributes to build the ORDER BY
            clause from.  See the `setOrder` method for details.
        :param conditions: the conditions to build the WHERE clause
            from.  See the `addConditions` method for details.
        :param includes: list of related objects to add to the INCLUDE
            clause.  See the `addIncludes` method for details.
        """

        super(Query, self).__init__()
        self.client = client

        if isinstance(entity, basestring):
            self.entity = getentityclassbyname(self.client, entity)
        elif issubclass(entity, icat.entity.Entity):
            if (entity in self.client.typemap.values() and 
                entity.BeanName is not None):
                self.entity = entity
            else:
                raise TypeError("Invalid entity type '%s'." % entity.__name__)
        else:
            raise TypeError("Invalid entity type '%s'." % type(entity))

        self.setOrder(order)
        self.conditions = dict()
        self.addConditions(conditions)
        self.includes = set()
        self.addIncludes(includes)

    def setOrder(self, order):
        """Set the order to build the ORDER BY clause from.

        :param order: the list of the attributes used for sorting.
            A special value of `True` may be used to indicate the
            natural order of the entity type.  Any `False` value
            means no ORDER BY clause.
        :type order: ``list`` of ``str`` or ``bool``
        :raise ValueError: if the order contains invalid attributes
            that either do not exist or contain one to many
            relationships.
        """
        if order is True:

            self.order = getnaturalorder(self.client, self.entity)

        elif order:

            self.order = []
            for obj in order:

                rclass = self.entity
                final = False
                for attr in obj.split('.'):

                    if final:
                        # Last component was attribute, no further
                        # components in the name allowed.
                        raise ValueError("Invalid attribute '%s' for %s." 
                                         % (obj, self.entity.BeanName))

                    attrInfo = rclass.getAttrInfo(self.client, attr)
                    if attrInfo.relType == "ATTRIBUTE":
                        final = True
                    elif attrInfo.relType == "ONE":
                        rclass = getentityclassbyname(self.client, attrInfo.type)
                    elif attrInfo.relType == "MANY":
                        raise ValueError("Cannot use one to many relationship "
                                         "in '%s' to order %s." 
                                         % (obj, self.entity.BeanName))
                    else:
                        assert False, "Invalid relType: '%s'" % attrInfo.relType

                if final:
                    # obj is an attribute, use it right away.
                    self.order.append(obj)
                else:
                    # obj is a related object, use the natural order
                    # of its class.
                    rorder = getnaturalorder(self.client, rclass)
                    self.order.extend(["%s.%s" % (obj, ra) for ra in rorder])

        else:

            self.order = []

    def addConditions(self, conditions):
        """Add conditions to the constraints to build the WHERE clause from.

        :param conditions: the conditions to restrict the search
            result.  This should be a mapping of attribute names to
            conditions on that attribute.  The latter may either be a
            string with a single condition or a list of strings to add
            more then one condition on a single attribute.  If the
            query already has a condition on a given attribute, it
            will be turned into a list with the new condition(s)
            appended.
        :type conditions: ``dict``
        """
        if conditions:
            for a in conditions.keys():
                if a in self.conditions:
                    conds = []
                    if isinstance(self.conditions[a], basestring):
                        conds.append(self.conditions[a])
                    else:
                        conds.extend(self.conditions[a])
                    if isinstance(conditions[a], basestring):
                        conds.append(conditions[a])
                    else:
                        conds.extend(conditions[a])
                    self.conditions[a] = conds
                else:
                    self.conditions[a] = conditions[a]

    def addIncludes(self, includes):
        """Add related objects to build the INCLUDE clause from.

        :param includes: list of related objects to add to the INCLUDE
            clause.
        :type includes: iterable of ``str``
        """
        if includes:
            self.includes.update(includes)

    def __repr__(self):
        """Return a formal representation of the query.
        """
        return ("%s(%s, %s, order=%s, conditions=%s, includes=%s)"
                % (self.__class__.__name__, 
                   repr(self.client), repr(self.entity), 
                   repr(self.order), repr(self.conditions), 
                   repr(self.includes)))

    def __str__(self):
        """Return a string representation of the query.
        """
        base = "SELECT o FROM %s o" % self.entity.BeanName
        joinattrs = set(self.order) | set(self.conditions.keys())
        subst = makesubst(joinattrs)
        joins = ""
        for obj in sorted(subst.keys()):
            joins += " JOIN %s" % dosubst(obj, subst)
        if self.conditions:
            conds = []
            for a in sorted(self.conditions.keys()):
                attr = dosubst(a, subst)
                cond = self.conditions[a]
                if isinstance(cond, basestring):
                    conds.append("%s %s" % (attr, cond))
                else:
                    for c in cond:
                        conds.append("%s %s" % (attr, c))
            where = " WHERE " + " AND ".join(conds)
        else:
            where = ""
        if self.order:
            orders = [ dosubst(a, subst) for a in self.order ]
            order = " ORDER BY " + ", ".join(orders)
        else:
            order = ""
        if self.includes:
            subst = makesubst(self.includes)
            self.addIncludes(subst.keys())
            incl = [ dosubst(obj, subst) for obj in sorted(self.includes) ]
            include = " INCLUDE " + ", ".join(incl)
        else:
            include = ""
        return base + joins + where + order + include