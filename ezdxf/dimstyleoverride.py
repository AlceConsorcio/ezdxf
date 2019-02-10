from typing import Any, TYPE_CHECKING, Tuple
from ezdxf.lldxf import const
from ezdxf.lldxf.const import DXFAttributeError, DIMJUST, DIMTAD
from ezdxf.render.arrows import ARROWS
from ezdxf.math import Vector
import logging

logger = logging.getLogger('ezdxf')

if TYPE_CHECKING:
    from ezdxf.eztypes import Dimension, UCS, Drawing, DimStyle, Vertex, BaseDimensionRenderer


class DimStyleOverride:
    def __init__(self, dimension: 'Dimension', override: dict = None):
        self.dimension = dimension  # type: Dimension
        dim_style_name = dimension.get_dxf_attrib('dimstyle', 'STANDARD')
        self.dimstyle = self.drawing.dimstyles.get(dim_style_name)  # type: DimStyle
        self.dimstyle_attribs = self.get_dstyle_dict()  # type: dict

        # special ezdxf attributes beyond the DXF reference, therefore not stored in the DSTYLE data.
        # This are only rendering effects or data transfer objects
        # user_location: Vector - user location override if not None
        # relative_user_location: bool - user location override relative to dimline center if True
        # text_shift_h: float - shift text in text direction, relative to standard text location
        # text_shift_v: float - shift text perpendicular to text direction, relative to standard text location
        self.update(override or {})

    @property
    def drawing(self) -> 'Drawing':
        return self.dimension.drawing

    @property
    def dxfversion(self) -> str:
        return self.dimension.drawing.dxfversion

    def get_dstyle_dict(self) -> dict:
        return self.dimension.get_acad_dstyle(self.dimstyle)

    def get(self, attribute: str, default: Any = None) -> Any:
        if attribute in self.dimstyle_attribs:
            result = self.dimstyle_attribs[attribute]
        else:
            # Return default value for attributes not supported by DXF R12.
            # This is a hack to use the same algorithm to render DXF R2000 and DXF R12 DIMENSION entities.
            # But the DXF R2000 attributes are not stored in the DXF R12 file!!!
            # Does not catch invalid attributes names! Look into debug log for ignored DIMSTYLE attributes.
            try:
                result = self.dimstyle.get_dxf_attrib(attribute, default)
            except DXFAttributeError:
                # return default value
                result = default
        return result

    def pop(self, attribute: str, default: Any = None) -> Any:
        value = self.get(attribute, default)
        # delete just from override dict
        del self[attribute]
        return value

    def update(self, attribs: dict) -> None:
        self.dimstyle_attribs.update(attribs)

    def __getitem__(self, item: str) -> Any:
        return self.get(item)

    def __setitem__(self, key: str, value: Any) -> None:
        self.dimstyle_attribs[key] = value

    def __delitem__(self, key: str) -> None:
        try:
            del self.dimstyle_attribs[key]
        except KeyError:  # silent discard
            pass

    def commit(self) -> None:
        """
        Write overwritten DIMSTYLE attributes into XDATA section of the DIMENSION entity.

        """
        def set_arrow_handle(attrib_name, block_name):
            attrib_name += '_handle'
            if block_name in ARROWS:  # create all arrows on demand
                block_name = ARROWS.create_block(blocks, block_name)
            if block_name == '_CLOSEDFILLED':  # special arrow
                handle = '0'  # set special #0 handle for closed filled arrow
            else:
                block = blocks.get(block_name)
                handle = block.block_record_handle
            self.dimstyle_attribs[attrib_name] = handle

        def set_linetype_handle(attrib_name, linetype_name):
            ltype = self.drawing.linetypes.get(linetype_name)
            self.dimstyle_attribs[attrib_name + '_handle'] = ltype.dxf.handle

        if self.drawing.dxfversion > 'AC1009':
            # transform block names into block record handles
            blocks = self.drawing.blocks
            for attrib_name in ('dimblk', 'dimblk1', 'dimblk2', 'dimldrblk'):
                try:
                    block_name = self.dimstyle_attribs.pop(attrib_name)
                except KeyError:
                    pass
                else:
                    set_arrow_handle(attrib_name, block_name)

        if self.drawing.dxfversion >= 'AC1021':
            # transform linetype names into LTYPE entry handles
            for attrib_name in ('dimltype', 'dimltex1', 'dimltex2'):
                try:
                    linetype_name = self.dimstyle_attribs.pop(attrib_name)
                except KeyError:
                    pass
                else:
                    set_linetype_handle(attrib_name, linetype_name)

        self.dimension.set_acad_dstyle(self.dimstyle_attribs)

    def set_arrows(self, blk: str = None, blk1: str = None, blk2: str = None, ldrblk: str = None,
                   size: float = None) -> None:
        """
        Set arrows or user defined blocks and disable oblique stroke as tick.

        Args:
            blk: defines both arrows at once as name str or user defined block (name)
            blk1: defines left arrow as name str or as user defined block (name)
            blk2: defines right arrow as name str or as user defined block (name)
            ldrblk: defines leader arrow as name str or as user defined block (name)
            size: arrow size in drawing units

        """

        def set_arrow(dimvar: str, name: str) -> None:
            self.dimstyle_attribs[dimvar] = name

        if size is not None:
            self.dimstyle_attribs['dimasz'] = float(size)
        if blk is not None:
            set_arrow('dimblk', blk)
            self.dimstyle_attribs['dimsah'] = 0
            self.dimstyle_attribs['dimtsz'] = 0.  # use arrows
        if blk1 is not None:
            set_arrow('dimblk1', blk1)
            self.dimstyle_attribs['dimsah'] = 1
            self.dimstyle_attribs['dimtsz'] = 0.  # use arrows
        if blk2 is not None:
            set_arrow('dimblk2', blk2)
            self.dimstyle_attribs['dimsah'] = 1
            self.dimstyle_attribs['dimtsz'] = 0.  # use arrows
        if ldrblk is not None:
            set_arrow('dimldrblk', ldrblk)

    def get_arrow_names(self) -> Tuple[str, str]:
        """
        Get arrows as name strings like 'ARCHTICK'.

        """
        dimtsz = self.get('dimtsz')
        blk1, blk2 = None, None
        if dimtsz == 0.:
            if bool(self.get('dimsah')):
                blk1 = self.get('dimblk1')
                blk2 = self.get('dimblk2')
            else:
                blk = self.get('dimblk')
                blk1 = blk
                blk2 = blk
        return blk1, blk2

    def set_tick(self, size: float = 1) -> None:
        """
        Use oblique stroke as tick, disables arrows.

        Args:
            size: arrow size in daring units

        """
        self.dimstyle_attribs['dimtsz'] = float(size)

    def set_text_align(self, halign=None, valign=None) -> None:
        """
        Set measurement text alignment, `halign` defines the horizontal alignment, `valign` defines the vertical
        alignment, `above1` and `above2` means above extension line 1 or 2 and aligned with extension line.

        Args:
            halign: `left`, `right` or `center`
            valign: `above`, `center`, `below`, `above1`, `above2`

        """
        if halign:
            self.dimstyle_attribs['dimjust'] = DIMJUST[halign.lower()]

        if valign:
            self.dimstyle_attribs['dimtad'] = DIMTAD[valign.lower()]

    def set_tolerance(self, upper: float, lower: float = None, hfactor: float = None,
                      align: str = None, dec: int = None, leading_zeros: bool = None,
                      trailing_zeros: bool = None) -> None:
        """
        Set tolerance text format, upper and lower value, text height factor, number of decimal places or leading and
        trailing zero suppression.

        Args:
            upper: upper tolerance value
            lower: lower tolerance value, if None same as upper
            hfactor: tolerance text height factor in relation to the dimension text height
            align: tolerance text alignment "TOP", "MIDDLE", "BOTTOM"
            dec: Sets the number of decimal places displayed
            leading_zeros: suppress leading zeros for decimal dimensions if False
            trailing_zeros: suppress trailing zeros for decimal dimensions if False

        """
        self.dimstyle_attribs['dimtol'] = 1
        self.dimstyle_attribs['dimlim'] = 0
        self.dimstyle_attribs['dimtp'] = float(upper)
        if lower is not None:
            self.dimstyle_attribs['dimtm'] = float(lower)
        else:
            self.dimstyle_attribs['dimtm'] = float(upper)
        if hfactor is not None:
            self.dimstyle_attribs['dimtfac'] = float(hfactor)
        if align is not None:
            self.dimstyle_attribs['dimtolj'] = const.MTEXT_INLINE_ALIGN[align.upper()]
        if dec is not None:
            self.dimstyle_attribs['dimtdec'] = dec

        # works only with decimal dimensions not inch and feet, US user set dimzin directly
        if leading_zeros is not None or trailing_zeros is not None:
            dimtzin = 0
            if leading_zeros is False:
                dimtzin = const.DIMZIN_SUPPRESSES_LEADING_ZEROS
            if trailing_zeros is False:
                dimtzin += const.DIMZIN_SUPPRESSES_TRAILING_ZEROS
            self.dimstyle_attribs['dimtzin'] = dimtzin

    def set_limits(self, upper: float, lower: float, hfactor: float = None,
                   dec: int = None, leading_zeros: bool = None, trailing_zeros: bool = None) -> None:
        """
        Set limits text format, upper and lower limit values, text height factor, number of decimal places or
        leading and trailing zero suppression.

        Args:
            upper: upper limit value added to measurement value
            lower: lower lower value subtracted from measurement value
            hfactor: limit text height factor in relation to the dimension text height
            dec: Sets the number of decimal places displayed, required DXF R2000+
            leading_zeros: suppress leading zeros for decimal dimensions if False, required DXF R2000+
            trailing_zeros: suppress trailing zeros for decimal dimensions if False, required DXF R2000+

        """
        # exclusive limits
        self.dimstyle_attribs['dimlim'] = 1
        self.dimstyle_attribs['dimtol'] = 0
        self.dimstyle_attribs['dimtp'] = float(upper)
        self.dimstyle_attribs['dimtm'] = float(lower)
        if hfactor is not None:
            self.dimstyle_attribs['dimtfac'] = float(hfactor)

        # works only with decimal dimensions not inch and feet, US user set dimzin directly
        if leading_zeros is not None or trailing_zeros is not None:
            dimtzin = 0
            if leading_zeros is False:
                dimtzin = const.DIMZIN_SUPPRESSES_LEADING_ZEROS
            if trailing_zeros is False:
                dimtzin += const.DIMZIN_SUPPRESSES_TRAILING_ZEROS
            self.dimstyle_attribs['dimtzin'] = dimtzin

        if dec is not None:
            self.dimstyle_attribs['dimtdec'] = int(dec)

    def set_text_format(self, prefix: str = '', postfix: str = '', rnd: float = None, dec: int = None, sep: str = None,
                        leading_zeros: bool = None, trailing_zeros: bool = None) -> None:
        """
        Set dimension text format, like prefix and postfix string, rounding rule and number of decimal places.

        Args:
            prefix: dimension text prefix text as string
            postfix: dimension text postfix text as string
            rnd: Rounds all dimensioning distances to the specified value, for instance, if DIMRND is set to 0.25, all
                 distances round to the nearest 0.25 unit. If you set DIMRND to 1.0, all distances round to the nearest
                 integer.
            dec: Sets the number of decimal places displayed for the primary units of a dimension. requires DXF R2000+
            sep: "." or "," as decimal separator
            leading_zeros: suppress leading zeros for decimal dimensions if False
            trailing_zeros: suppress trailing zeros for decimal dimensions if False

        """
        if prefix or postfix:
            self.dimstyle_attribs['dimpost'] = prefix + '<>' + postfix
        if rnd is not None:
            self.dimstyle_attribs['dimrnd'] = rnd
        if dec is not None:
            self.dimstyle_attribs['dimdec'] = dec
        if sep is not None:
            self.dimstyle_attribs['dimdsep'] = ord(sep)
        # works only with decimal dimensions not inch and feet, US user set dimzin directly
        if leading_zeros is not None or trailing_zeros is not None:
            dimzin = 0
            if leading_zeros is False:
                dimzin = const.DIMZIN_SUPPRESSES_LEADING_ZEROS
            if trailing_zeros is False:
                dimzin += const.DIMZIN_SUPPRESSES_TRAILING_ZEROS
            self.dimstyle_attribs['dimzin'] = dimzin

    def set_dimline_format(self, color: int = None, linetype: str = None, lineweight: int = None,
                           extension: float = None, disable1: bool = None, disable2: bool = None):
        """
        Set dimension line properties

        Args:
            color: color index
            linetype: linetype as string
            lineweight: line weight as int, 13 = 0.13mm, 200 = 2.00mm
            extension: extension length
            disable1: True to suppress first part of dimension line
            disable2: True to suppress second part of dimension line

        """
        if color is not None:
            self.dimstyle_attribs['dimclrd'] = color
        if linetype is not None:
            self.dimstyle_attribs['dimltype'] = linetype
        if lineweight is not None:
            self.dimstyle_attribs['dimlwd'] = lineweight
        if extension is not None:
            self.dimstyle_attribs['dimdle'] = extension
        if disable1 is not None:
            self.dimstyle_attribs['dimsd1'] = disable1
        if disable2 is not None:
            self.dimstyle_attribs['dimsd2'] = disable2

    def set_extline_format(self, color: int = None, lineweight: int = None, extension: float = None,
                           offset: float = None, fixed_length: float = None):
        """
        Set common extension line attributes.

        Args:
            color: color index
            lineweight: line weight as int, 13 = 0.13mm, 200 = 2.00mm
            extension: extension length above dimension line
            offset: offset from measurement point
            fixed_length: set fixed length extension line, length below the dimension line

        """
        if color is not None:
            self.dimstyle_attribs['dimclre'] = color
        if lineweight is not None:
            self.dimstyle_attribs['dimlwe'] = lineweight
        if extension is not None:
            self.dimstyle_attribs['dimexe'] = extension
        if offset is not None:
            self.dimstyle_attribs['dimexo'] = offset
        if fixed_length is not None:
            self.dimstyle_attribs['dimflxon'] = 1
            self.dimstyle_attribs['dimflx'] = fixed_length

    def set_extline1(self, linetype: str = None, disable=False):
        """
        Set extension line 1 attributes.

        Args:
            linetype: linetype for extension line 1
            disable: disable extension line 1 if True

        """
        if linetype is not None:
            self.dimstyle_attribs['dimltex1'] = linetype
        if disable:
            self.dimstyle_attribs['dimse1'] = 1

    def set_extline2(self, linetype: str = None, disable=False):
        """
        Set extension line 2 attributes.

        Args:
            linetype: linetype for extension line 2
            disable: disable extension line 2 if True

        """
        if linetype is not None:
            self.dimstyle_attribs['dimltex2'] = linetype
        if disable:
            self.dimstyle_attribs['dimse2'] = 1

    def set_text(self, text='<>') -> None:
        """
        Set dimension text.

            - text == ' ' ... suppress dimension text
            - text == '' or '<>' ... use measured distance as dimension text
            - else use text literally

        Args:
            text: string

        """
        self.dimension.dxf.text = text

    def shift_text(self, dh: float, dv: float) -> None:
        """
        Set relative text movement, this is not a DXF feature, therefor parameter not stored in the XDATA DSTYLE
        section. This is only a rendering effect and ignored if a user defined location is in use.

        Args:
            dh: shift text in text direction
            dv: shift text perpendicular to text direction

        """
        self.dimstyle_attribs['text_shift_h'] = dh
        self.dimstyle_attribs['text_shift_v'] = dv

    def set_location(self, location: 'Vertex', leader=False, relative=False):
        self.dimstyle_attribs['dimtmove'] = 1 if leader else 2
        self.dimension.set_flag_state(self.dimension.USER_LOCATION_OVERRIDE, state=True, name='dimtype')
        self.dimstyle_attribs['user_location'] = Vector(location)
        self.dimstyle_attribs['relative_user_location'] = relative

    def get_renderer(self, ucs: 'UCS' = None):
        return self.drawing.dimension_renderer.dispatch(self, ucs)

    def render(self, ucs: 'UCS' = None, discard=False) -> 'BaseDimensionRenderer':
        """
        Initiate dimension line rendering process and also writes overridden dimension style attributes into the DSTYLE
        XDATA section.

        For a friendly CAD applications like BricsCAD you can discard the dimension line rendering, because it is done
        automatically by BricsCAD, if no dimension rendering BLOCK is available and it is likely to get better results
        as by ezdxf.

        AutoCAD does not render DIMENSION entities automatically, so I rate AutoCAD as unfriendly CAD application.

        Args:
            ucs: user coordinate system
            discard: discard rendering done by ezdxf (works with BricsCAD, but not with AutoCAD)

        Returns: used renderer for analytics

        """

        renderer = self.get_renderer(ucs)
        if discard:
            self.drawing.add_acad_incompatibility_message('DIMENSION without geometry as BLOCK (discard=True)')
        else:
            block = self.drawing.blocks.new_anonymous_block(type_char='D')
            self.dimension.dxf.geometry = block.name
            renderer.render(block)

        # should be called after rendering
        renderer.finalize()

        if len(self.dimstyle_attribs):
            self.commit()
        return renderer